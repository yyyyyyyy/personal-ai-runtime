"""Email MCP Server — IMAP read-only access with SMTP send capability."""

import email
import imaplib
import json
import smtplib
from email.header import decode_header
from email.mime.text import MIMEText


class EmailServer:
    """Email operations: read inbox via IMAP, send via SMTP (requires approval)."""

    def __init__(self):
        self._imap_host = "imap.gmail.com"
        self._smtp_host = "smtp.gmail.com"

    def _get_credentials(self):
        import os
        return os.getenv("EMAIL_USER", ""), os.getenv("EMAIL_PASS", "")

    def check_inbox(self, limit: int = 10, unread_only: bool = True) -> str:
        """Check inbox for recent emails."""
        user, password = self._get_credentials()
        if not user or not password:
            return json.dumps({"error": "Email credentials not configured (EMAIL_USER/EMAIL_PASS)"})

        try:
            mail = imaplib.IMAP4_SSL(self._imap_host, timeout=15)
            mail.login(user, password)
            mail.select("inbox")

            search_criteria = "UNSEEN" if unread_only else "ALL"
            status, message_ids = mail.search(None, search_criteria)

            emails = []
            ids = message_ids[0].split()
            for msg_id in ids[-limit:]:
                status, msg_data = mail.fetch(msg_id, "(RFC822)")
                for response_part in msg_data:
                    if isinstance(response_part, tuple):
                        msg = email.message_from_bytes(response_part[1])
                        subject, encoding = decode_header(msg["Subject"])[0]
                        if isinstance(subject, bytes):
                            subject = subject.decode(encoding or "utf-8", errors="replace")

                        body = ""
                        if msg.is_multipart():
                            for part in msg.walk():
                                if part.get_content_type() == "text/plain":
                                    payload = part.get_payload(decode=True)
                                    if payload:
                                        body += payload.decode("utf-8", errors="replace")[:500]
                        else:
                            payload = msg.get_payload(decode=True)
                            if payload:
                                body = payload.decode("utf-8", errors="replace")[:500]

                        emails.append({
                            "from": decode_header(msg["From"])[0][0] if isinstance(decode_header(msg["From"])[0][0], str) else (decode_header(msg["From"])[0][0]).decode("utf-8", errors="replace"),
                            "subject": subject,
                            "date": msg["Date"],
                            "preview": body[:200],
                        })

            mail.logout()
            return json.dumps({"count": len(emails), "unread_only": unread_only, "emails": emails})

        except imaplib.IMAP4.error as e:
            return json.dumps({"error": f"IMAP login failed: {str(e)}"})
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

            server = smtplib.SMTP_SSL(self._smtp_host, 465, timeout=15)
            server.login(user, password)
            server.sendmail(user, [to], msg.as_string())
            server.quit()

            return json.dumps({"success": True, "to": to, "subject": subject})
        except Exception as e:
            return json.dumps({"error": str(e)})


email_server = EmailServer()
