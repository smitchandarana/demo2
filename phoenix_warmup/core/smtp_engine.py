"""
core/smtp_engine.py
SMTP email sending via Zoho (smtp.zoho.in:587, STARTTLS).
Returns structured results; never raises to caller.
Plain text only. No HTML. No links.
"""
import smtplib
import ssl
import time
from dataclasses import dataclass, field
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr, make_msgid
from typing import Optional


# SMTP response codes classified as hard bounces (permanent failures)
HARD_BOUNCE_CODES = {550, 551, 552, 553, 554, 555}
# Soft bounces (temporary, may retry)
SOFT_BOUNCE_CODES = {421, 450, 451, 452}

CONNECT_TIMEOUT = 30  # seconds


@dataclass
class SendResult:
    success: bool
    message_id: str = ""
    error_code: Optional[int] = None
    error_message: str = ""
    duration_ms: int = 0
    is_hard_bounce: bool = False
    is_soft_bounce: bool = False
    is_auth_failure: bool = False


class SMTPEngine:
    """
    Handles SMTP connection and email sending for a single inbox.
    Each send() call creates a fresh connection (no persistent sessions).
    """

    def __init__(
        self,
        host: str,
        port: int,
        email: str,
        password: str,
        display_name: str = "",
    ) -> None:
        self.host = host
        self.port = port
        self.email = email
        self.password = password
        self.display_name = display_name or email

    def send(
        self,
        to_email: str,
        to_name: str,
        subject: str,
        body: str,
        in_reply_to: Optional[str] = None,
        references: Optional[str] = None,
    ) -> SendResult:
        """
        Send one plain-text email via STARTTLS.
        Returns a SendResult regardless of outcome — never raises.
        """
        start = time.monotonic()
        msg_id = make_msgid(domain=self.email.split("@")[-1])

        # Build MIME message — plain text only, no HTML
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = formataddr((self.display_name, self.email))
        msg["To"] = formataddr((to_name, to_email))
        msg["Message-ID"] = msg_id
        msg["X-Mailer"] = "Microsoft Outlook 16.0"
        if in_reply_to:
            msg["In-Reply-To"] = in_reply_to
            msg["References"] = references or in_reply_to

        try:
            ctx = ssl.create_default_context()
            with smtplib.SMTP(self.host, self.port, timeout=CONNECT_TIMEOUT) as smtp:
                smtp.ehlo()
                smtp.starttls(context=ctx)
                smtp.ehlo()
                smtp.login(self.email, self.password)
                smtp.sendmail(self.email, [to_email], msg.as_string())

            return SendResult(
                success=True,
                message_id=msg_id,
                duration_ms=int((time.monotonic() - start) * 1000),
            )

        except smtplib.SMTPRecipientsRefused as exc:
            code, reason_bytes = list(exc.recipients.values())[0]
            reason = (reason_bytes.decode("utf-8", errors="replace")
                      if isinstance(reason_bytes, bytes) else str(reason_bytes))
            return SendResult(
                success=False,
                error_code=code,
                error_message=reason,
                duration_ms=int((time.monotonic() - start) * 1000),
                is_hard_bounce=code in HARD_BOUNCE_CODES,
                is_soft_bounce=code in SOFT_BOUNCE_CODES,
            )

        except smtplib.SMTPAuthenticationError as exc:
            return SendResult(
                success=False,
                error_code=535,
                error_message=f"Authentication failed: {exc.smtp_error!r}",
                duration_ms=int((time.monotonic() - start) * 1000),
                is_auth_failure=True,
            )

        except smtplib.SMTPConnectError as exc:
            return SendResult(
                success=False,
                error_message=f"Connection refused: {exc}",
                duration_ms=int((time.monotonic() - start) * 1000),
                is_soft_bounce=True,
            )

        except (smtplib.SMTPException, TimeoutError, OSError) as exc:
            return SendResult(
                success=False,
                error_message=str(exc),
                duration_ms=int((time.monotonic() - start) * 1000),
                is_soft_bounce=True,
            )

    def test_connection(self) -> tuple:
        """
        Quick auth probe: connect, STARTTLS, login, disconnect.
        Returns (success: bool, message: str).
        Used by the UI when adding/testing an inbox.
        """
        try:
            ctx = ssl.create_default_context()
            with smtplib.SMTP(self.host, self.port, timeout=CONNECT_TIMEOUT) as smtp:
                smtp.ehlo()
                smtp.starttls(context=ctx)
                smtp.ehlo()
                smtp.login(self.email, self.password)
            return True, "SMTP connection successful"
        except smtplib.SMTPAuthenticationError:
            return False, "Authentication failed — check your app password"
        except smtplib.SMTPConnectError:
            return False, f"Cannot connect to {self.host}:{self.port}"
        except Exception as exc:
            return False, str(exc)
