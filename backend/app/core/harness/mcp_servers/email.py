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
        result: set[str] = set()
        for msg_id in ids:
            _status, msg_data = mail.fetch(
                msg_id,
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

        entries: list[tuple[float, dict]] = []
        ids = message_ids[0].split() if message_ids[0] else []
        pool_size = min(len(ids), max(limit * 5, 50))
        for msg_id in ids[-pool_size:]:
            _status, msg_data = mail.fetch(msg_id, "(RFC822)")
            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])
                    from_raw = _decode_mime_header(msg.get("From"))
                    subject = _decode_mime_header(msg.get("Subject")) or "(无主题)"
                    body = _extract_body(msg, max_len=body_max)
                    date_raw = msg.get("Date")
                    try:
                        ts = (
                            parsedate_to_datetime(date_raw).timestamp()
                            if date_raw
                            else 0.0
                        )
                    except Exception:
                        ts = 0.0

                    entries.append((ts, {
                        "message_id": _stable_message_id(msg, from_raw, subject, date_raw),
                        "from": from_raw,
                        "subject": subject,
                        "date": _format_date(date_raw),
                        "preview": body[:200] if body else "",
                        "body": body,
                    }))

        entries.sort(key=lambda item: item[0], reverse=True)
        return [item[1] for item in entries[:limit]]

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
                {k: v for k, v in em.items() if k != "body"}
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
                "body": em.get("body") or em.get("preview", ""),
            }, ensure_ascii=False)
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
