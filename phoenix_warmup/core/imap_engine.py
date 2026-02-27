"""
core/imap_engine.py
IMAP inbox scanning via Zoho (imap.zoho.in:993, SSL).
Fetches unseen messages, parses them, marks as seen.
"""
import email as email_lib
import email.utils
import time
from dataclasses import dataclass
from typing import List, Optional

try:
    import imapclient
    from imapclient import IMAPClient
    from imapclient.exceptions import IMAPClientError
    _IMAP_AVAILABLE = True
except ImportError:
    _IMAP_AVAILABLE = False
    IMAPClient = None
    IMAPClientError = Exception

CONNECT_TIMEOUT = 30  # seconds


@dataclass
class FetchedMessage:
    uid: int
    message_id: str
    subject: str
    from_email: str
    from_name: str
    body_text: str
    date_str: str


class IMAPEngine:
    """
    Manages a single IMAP connection for one inbox.
    Creates a fresh connection per operation (no persistent sessions).
    """

    def __init__(
        self,
        host: str,
        port: int,
        email: str,
        password: str,
    ) -> None:
        self.host = host
        self.port = port
        self.email = email
        self.password = password

    def _connect(self) -> "IMAPClient":
        """Create and authenticate an IMAPClient. Caller must close it."""
        if not _IMAP_AVAILABLE:
            raise RuntimeError("imapclient package is not installed")
        client = IMAPClient(
            host=self.host,
            port=self.port,
            ssl=True,
            timeout=CONNECT_TIMEOUT,
        )
        client.login(self.email, self.password)
        return client

    def fetch_unseen(self, folder: str = "INBOX") -> List[FetchedMessage]:
        """
        Connect to IMAP, select folder, fetch UNSEEN messages.
        Marks each fetched message as SEEN.
        Returns list of FetchedMessage dicts.
        Returns empty list on any error.
        """
        if not _IMAP_AVAILABLE:
            return []

        client = None
        try:
            client = self._connect()
            client.select_folder(folder)
            uids = client.search(["UNSEEN"])
            if not uids:
                return []

            messages = []
            # Fetch in batches of 10 to avoid large responses
            for i in range(0, len(uids), 10):
                batch = uids[i:i + 10]
                response = client.fetch(batch, ["RFC822", "FLAGS"])
                for uid, data in response.items():
                    raw_msg = data[b"RFC822"]
                    parsed = email_lib.message_from_bytes(raw_msg)
                    fetched = self._parse_message(uid, parsed)
                    messages.append(fetched)
                # Mark batch as seen
                try:
                    client.set_flags(batch, [imapclient.SEEN])
                except Exception:
                    pass  # Non-critical

            return messages

        except (IMAPClientError, OSError, TimeoutError, RuntimeError):
            return []
        finally:
            # Always close the connection regardless of success or exception
            if client is not None:
                try:
                    client.logout()
                except Exception:
                    pass

    def _parse_message(
        self,
        uid: int,
        msg: email_lib.message.Message,
    ) -> FetchedMessage:
        """Extract key fields from a parsed email message."""
        subject = str(msg.get("Subject", "")).strip()
        msg_id = str(msg.get("Message-ID", "")).strip()
        from_header = str(msg.get("From", ""))
        date_str = str(msg.get("Date", ""))

        from_name, from_email = email_lib.utils.parseaddr(from_header)

        # Extract plain text body
        body_text = ""
        if msg.is_multipart():
            for part in msg.walk():
                ct = part.get_content_type()
                if ct == "text/plain" and not part.get_filename():
                    charset = part.get_content_charset() or "utf-8"
                    payload = part.get_payload(decode=True)
                    if payload:
                        body_text = payload.decode(charset, errors="replace")
                    break
        else:
            if msg.get_content_type() == "text/plain":
                charset = msg.get_content_charset() or "utf-8"
                payload = msg.get_payload(decode=True)
                if payload:
                    body_text = payload.decode(charset, errors="replace")

        return FetchedMessage(
            uid=uid,
            message_id=msg_id,
            subject=subject,
            from_email=from_email.lower(),
            from_name=from_name,
            body_text=body_text[:2000],  # Cap at 2KB
            date_str=date_str,
        )

    def test_connection(self) -> tuple:
        """
        Quick IMAP credential check.
        Returns (success: bool, message: str).
        """
        if not _IMAP_AVAILABLE:
            return False, "imapclient package not installed"
        try:
            client = self._connect()
            client.select_folder("INBOX")
            client.logout()
            return True, "IMAP connection successful"
        except IMAPClientError as exc:
            return False, str(exc)
        except Exception as exc:
            return False, str(exc)
