"""Email MCP Server — IMAP read-only access with SMTP send capability."""

import email
import hashlib
import html
import imaplib
import json
import os
import re
import smtplib
from datetime import timezone
from email.header import decode_header
from email.mime.text import MIMEText
from email.utils import parsedate_to_datetime


def _decode_mime_header(value: str | None) -> str:
    if not value:
        return ""
    parts = decode_header(value)
    decoded: list[str] = []
    for fragment, encoding in parts:
        if isinstance(fragment, bytes):
            decoded.append(fragment.decode(encoding or "utf-8", errors="replace"))
        else:
            decoded.append(fragment)
    return "".join(decoded).strip()


def _strip_html(text: str) -> str:
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return html.unescape(text.strip())


def _stable_message_id(msg: email.message.Message, from_raw: str, subject: str, date_raw: str | None) -> str:
    header_id = (msg.get("Message-ID") or "").strip()
    if header_id:
        return header_id
    digest = hashlib.sha1(
        f"{from_raw}|{subject}|{date_raw or ''}".encode("utf-8"),
        usedforsecurity=False,
    ).hexdigest()
    return f"sha1:{digest}"


def _format_date(date_str: str | None) -> str:
    if not date_str:
        return ""
    try:
        dt = parsedate_to_datetime(date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dt = dt.astimezone()
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return date_str[:20] if date_str else ""


def _extract_body(msg: email.message.Message, max_len: int = 300) -> str:
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if isinstance(payload, bytes):
                    body += payload.decode("utf-8", errors="replace")
                    break
        if not body:
            for part in msg.walk():
                if part.get_content_type() == "text/html":
                    payload = part.get_payload(decode=True)
                    if isinstance(payload, bytes):
                        body = _strip_html(payload.decode("utf-8", errors="replace"))
                        break
    else:
        payload = msg.get_payload(decode=True)
        if isinstance(payload, bytes):
            raw = payload.decode("utf-8", errors="replace")
            body = _strip_html(raw) if "<" in raw and ">" in raw else raw
    return body[:max_len].strip()


class EmailServer:
    """Email operations: read inbox via IMAP, send via SMTP (requires approval)."""

    def __init__(self):
        self._refresh_config()

    def _refresh_config(self):
        from app.core.runtime.runtime_config import runtime_config

        creds = runtime_config.get_email_credentials()
        self._imap_host = str(creds.get("imap_host") or os.getenv("EMAIL_IMAP_HOST", "imap.gmail.com"))
        self._smtp_host = str(creds.get("smtp_host") or os.getenv("EMAIL_SMTP_HOST", "smtp.gmail.com"))
        self._smtp_port = int(str(creds.get("smtp_port") or os.getenv("EMAIL_SMTP_PORT", "465")))
        self._user = str(creds.get("user") or os.getenv("EMAIL_USER", ""))
        self._password = str(creds.get("password") or os.getenv("EMAIL_PASS", ""))

    def _get_credentials(self):
        self._refresh_config()
        return self._user, self._password

    def _connect_inbox(self) -> imaplib.IMAP4_SSL:
        user, password = self._get_credentials()
        if not user or not password:
            raise ValueError("Email credentials not configured (EMAIL_USER/EMAIL_PASS)")

        mail = imaplib.IMAP4_SSL(self._imap_host, timeout=15)
        mail.login(user, password)
        mail.select("inbox")
        return mail

    @staticmethod
    def _message_id_from_header_bytes(header_bytes: bytes) -> str:
        msg = email.message_from_bytes(header_bytes)
        from_raw = _decode_mime_header(msg.get("From"))
        subject = _decode_mime_header(msg.get("Subject")) or "(无主题)"
        date_raw = msg.get("Date")
        return _stable_message_id(msg, from_raw, subject, date_raw)

    def _fetch_unread_message_ids_connected(self, mail: imaplib.IMAP4_SSL) -> set[str]:
        """Stable message_id for every UNSEEN message (header-only fetch)."""
        _status, message_ids = mail.search(None, "UNSEEN")
        ids = message_ids[0].split() if message_ids[0] else []
        if not ids:
            return set()

        result: set[str] = set()
        # Batch fetch in chunks to avoid extremely long command lines
        for i in range(0, len(ids), 100):
            chunk = ids[i : i + 100]
            id_range = ",".join(tid.decode() for tid in chunk)
            _status, msg_data = mail.fetch(
                id_range,
                "(BODY.PEEK[HEADER.FIELDS (MESSAGE-ID FROM SUBJECT DATE)])",
            )
            for response_part in msg_data:
                if isinstance(response_part, tuple) and response_part[1]:
                    result.add(self._message_id_from_header_bytes(response_part[1]))
        return result

    def _fetch_sorted_emails_connected(
        self,
        mail: imaplib.IMAP4_SSL,
        limit: int,
        unread_only: bool,
        body_max: int = 300,
    ) -> list[dict]:
        search_criteria = "UNSEEN" if unread_only else "ALL"
        _status, message_ids = mail.search(None, search_criteria)

        ids = message_ids[0].split() if message_ids[0] else []
        if not ids:
            return []

        # 1. Fetch headers and internaldate for a pool of candidates in one batch.
        # This is much faster than fetching full RFC822 for each candidate.
        pool_size = min(len(ids), max(limit * 5, 50))
        target_ids = ids[-pool_size:]
        id_range = ",".join(tid.decode() for tid in target_ids)

        # Use BODY.PEEK to avoid marking as read during list/preview.
        _status, msg_data = mail.fetch(
            id_range,
            "(INTERNALDATE BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE MESSAGE-ID)])"
        )

        candidates: list[dict] = []
        # msg_data can contain tuples and bytes (closing parens).
        for part in msg_data:
            if not isinstance(part, tuple):
                continue

            header_content = part[1]
            msg = email.message_from_bytes(header_content)

            info = part[0].decode(errors="ignore")
            seq_match = re.search(r"^(\d+)", info)
            if not seq_match:
                continue
            seq_num = seq_match.group(1)

            # Internal date for sorting
            ts = 0.0
            idate_match = re.search(r'INTERNALDATE "([^"]+)"', info)
            if idate_match:
                try:
                    ts = parsedate_to_datetime(idate_match.group(1)).timestamp()
                except Exception:
                    pass

            from_raw = _decode_mime_header(msg.get("From"))
            subject = _decode_mime_header(msg.get("Subject")) or "(无主题)"
            date_raw = msg.get("Date")

            if ts == 0.0 and date_raw:
                try:
                    ts = parsedate_to_datetime(date_raw).timestamp()
                except Exception:
                    pass

            candidates.append({
                "seq_num": seq_num,
                "ts": ts,
                "message_id": _stable_message_id(msg, from_raw, subject, date_raw),
                "from": from_raw,
                "subject": subject,
                "date_raw": date_raw,
            })

        # 2. Sort candidates by date descending
        candidates.sort(key=lambda x: x["ts"], reverse=True)
        top_candidates = candidates[:limit]
        if not top_candidates:
            return []

        # 3. Fetch bodies only for the top candidates in another batch.
        top_ids = ",".join(c["seq_num"] for c in top_candidates)
        # Fetching full message content without marking as SEEN.
        _status, body_data = mail.fetch(top_ids, "(BODY.PEEK[])")

        body_map: dict[str, str] = {}
        for part in body_data:
            if isinstance(part, tuple):
                info = part[0].decode(errors="ignore")
                seq_match = re.search(r"^(\d+)", info)
                if seq_match:
                    s_num = seq_match.group(1)
                    m = email.message_from_bytes(part[1])
                    body_map[s_num] = _extract_body(m, max_len=body_max)

        results = []
        for c in top_candidates:
            body = body_map.get(c["seq_num"], "")
            results.append({
                "seq_num": c["seq_num"],  # IMAP sequence; strip before LLM-facing payloads
                "message_id": c["message_id"],
                "from": c["from"],
                "subject": c["subject"],
                "date": _format_date(c["date_raw"]),
                "preview": body[:200] if body else "",
                "body": body,
            })

        return results

    def _fetch_sorted_emails(
        self,
        limit: int,
        unread_only: bool,
        body_max: int = 300,
    ) -> list[dict]:
        mail = self._connect_inbox()
        try:
            return self._fetch_sorted_emails_connected(mail, limit, unread_only, body_max)
        finally:
            try:
                mail.logout()
            except Exception:
                import logging
                logging.getLogger(__name__).warning("Error during IMAP logout", exc_info=True)

    def check_inbox(self, limit: int = 10, unread_only: bool = False) -> str:
        """Check inbox for recent emails (default: all mail, not unread-only)."""
        try:
            mail = self._connect_inbox()
            try:
                all_unread_message_ids: list[str] | None = None
                if unread_only:
                    all_unread_message_ids = sorted(
                        self._fetch_unread_message_ids_connected(mail)
                    )
                emails = self._fetch_sorted_emails_connected(
                    mail, limit, unread_only, body_max=300
                )
            finally:
                try:
                    mail.logout()
                except Exception:
                    pass

            slim = [
                {k: v for k, v in em.items() if k not in ("body", "seq_num")}
                for em in emails
            ]
            payload: dict = {
                "count": len(slim),
                "unread_only": unread_only,
                "emails": slim,
            }
            if all_unread_message_ids is not None:
                payload["all_unread_message_ids"] = all_unread_message_ids
            return json.dumps(payload, ensure_ascii=False)
        except imaplib.IMAP4.error as e:
            return json.dumps({"error": f"IMAP login failed: {str(e)}"})
        except ValueError as e:
            return json.dumps({"error": str(e)})
        except Exception as e:
            return json.dumps({"error": str(e)})

    def read_inbox_email(
        self,
        index: int = 1,
        limit: int = 30,
        unread_only: bool = False,
    ) -> str:
        """Read one email by 1-based index (1 = newest among recent messages)."""
        try:
            emails = self._fetch_sorted_emails(limit, unread_only, body_max=4000)
            if not emails:
                return json.dumps({"error": "收件箱中没有邮件"})
            if index < 1 or index > len(emails):
                return json.dumps({
                    "error": f"序号 {index} 超出范围，当前共 {len(emails)} 封（1=最新）",
                })
            em = emails[index - 1]
            return json.dumps({
                "index": index,
                "total": len(emails),
                "from": em["from"],
                "subject": em["subject"],
                "date": em["date"],
                "message_id": em.get("message_id", ""),
                "body": em.get("body") or em.get("preview", ""),
            }, ensure_ascii=False)
        except imaplib.IMAP4.error as e:
            return json.dumps({"error": f"IMAP login failed: {str(e)}"})
        except ValueError as e:
            return json.dumps({"error": str(e)})
        except Exception as e:
            return json.dumps({"error": str(e)})

    def mark_inbox_email_read(
        self,
        index: int | None = None,
        message_id: str | None = None,
        limit: int = 30,
        unread_only: bool = True,
    ) -> str:
        """Mark one inbox message as read (IMAP \\Seen).

        Prefer ``message_id`` when known; otherwise ``index`` (1=newest) within
        the same listing window used by check_inbox/read_inbox_email.
        """
        mid = (message_id or "").strip()
        if not mid and index is None:
            return json.dumps({
                "error": "Provide message_id or index (1=newest among recent mail)",
            })
        try:
            mail = self._connect_inbox()
            try:
                emails = self._fetch_sorted_emails_connected(
                    mail, limit, unread_only, body_max=0
                )
                if not emails:
                    return json.dumps({"error": "收件箱中没有可标记的邮件"})

                target = None
                if mid:
                    for em in emails:
                        if em.get("message_id") == mid:
                            target = em
                            break
                    if target is None:
                        return json.dumps({
                            "error": f"未在最近 {limit} 封中找到 message_id={mid}",
                        })
                else:
                    assert index is not None
                    if index < 1 or index > len(emails):
                        return json.dumps({
                            "error": f"序号 {index} 超出范围，当前共 {len(emails)} 封（1=最新）",
                        })
                    target = emails[index - 1]

                seq = target.get("seq_num")
                if not seq:
                    return json.dumps({"error": "Internal error: missing IMAP sequence"})

                status, _data = mail.store(str(seq), "+FLAGS", "\\Seen")
                if status != "OK":
                    return json.dumps({"error": f"IMAP STORE failed: {status}"})

                return json.dumps({
                    "success": True,
                    "message_id": target.get("message_id", ""),
                    "from": target.get("from", ""),
                    "subject": target.get("subject", ""),
                    "index": index,
                }, ensure_ascii=False)
            finally:
                try:
                    mail.logout()
                except Exception:
                    pass
        except imaplib.IMAP4.error as e:
            return json.dumps({"error": f"IMAP login failed: {str(e)}"})
        except ValueError as e:
            return json.dumps({"error": str(e)})
        except Exception as e:
            return json.dumps({"error": str(e)})

    def send_email(self, to: str, subject: str, body: str) -> str:
        """Send an email via SMTP (requires user approval)."""
        user, password = self._get_credentials()
        if not user or not password:
            return json.dumps({"error": "Email credentials not configured"})

        try:
            msg = MIMEText(body)
            msg["Subject"] = subject
            msg["From"] = user
            msg["To"] = to

            server = smtplib.SMTP_SSL(self._smtp_host, self._smtp_port, timeout=15)
            server.login(user, password)
            server.sendmail(user, [to], msg.as_string())
            server.quit()

            return json.dumps({"success": True, "to": to, "subject": subject})
        except Exception as e:
            return json.dumps({"error": str(e)})


email_server = EmailServer()
