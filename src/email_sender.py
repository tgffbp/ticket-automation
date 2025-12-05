"""
Email sender module for the Ticket Automation System.

Implements secure email sending via SMTP with TLS.
Designed for use with Gmail App Passwords.
"""

import logging
import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from .config import EmailConfig


logger = logging.getLogger(__name__)


class EmailSenderError(Exception):
    """Error during email sending."""
    pass


class SMTPEmailSender:
    """
    SMTP-based email sender with TLS encryption.
    
    Designed for Gmail with App Password authentication.
    Also compatible with other SMTP providers (Outlook, etc.).
    
    Security:
        - Uses STARTTLS for encryption
        - Credentials loaded from environment variables
        - App Password recommended over regular password
    """
    
    def __init__(self, config: EmailConfig):
        """
        Initialize SMTP sender.
        
        Args:
            config: Email configuration with SMTP settings.
        """
        self._config = config
    
    def send(
        self,
        to_email: str,
        subject: str,
        body: str,
        attachments: list[Path] | None = None,
    ) -> bool:
        """
        Send email via SMTP with TLS.
        
        Args:
            to_email: Recipient email address.
            subject: Email subject line.
            body: Email body (plain text).
            attachments: Optional list of file paths to attach.
            
        Returns:
            True if sent successfully.
            
        Raises:
            EmailSenderError: If sending fails.
        """
        logger.info(f"Sending email to {to_email} via SMTP")
        
        try:
            # Create message
            msg = MIMEMultipart()
            msg["From"] = f"{self._config.from_name} <{self._config.from_email}>"
            msg["To"] = to_email
            msg["Subject"] = subject
            
            # Add body
            msg.attach(MIMEText(body, "plain", "utf-8"))
            
            # Add attachments
            if attachments:
                for file_path in attachments:
                    self._attach_file(msg, file_path)
            
            # Send via SMTP with TLS
            with smtplib.SMTP(self._config.smtp_host, self._config.smtp_port) as server:
                if self._config.smtp_use_tls:
                    server.starttls()
                
                server.login(
                    self._config.smtp_username,
                    self._config.smtp_password
                )
                server.send_message(msg)
            
            logger.info(f"Email sent successfully to {to_email}")
            return True
            
        except smtplib.SMTPAuthenticationError as e:
            logger.error(f"SMTP authentication failed: {e}")
            raise EmailSenderError(
                "SMTP authentication failed. "
                "For Gmail, ensure you're using an App Password."
            ) from e
        except smtplib.SMTPException as e:
            logger.error(f"SMTP error: {e}")
            raise EmailSenderError(f"SMTP error: {e}") from e
        except Exception as e:
            logger.error(f"Unexpected error sending email: {e}")
            raise EmailSenderError(f"Failed to send email: {e}") from e
    
    def _attach_file(self, msg: MIMEMultipart, file_path: Path) -> None:
        """Attach a file to the email."""
        if not file_path.exists():
            raise EmailSenderError(f"Attachment not found: {file_path}")
        
        with open(file_path, "rb") as f:
            part = MIMEApplication(f.read(), Name=file_path.name)
        
        part["Content-Disposition"] = f'attachment; filename="{file_path.name}"'
        msg.attach(part)
        logger.debug(f"Attached file: {file_path.name}")


def build_report_email_body(
    request_count: int,
    codebase_link: str,
) -> str:
    """
    Build the email body for the classification report.
    
    Args:
        request_count: Number of classified requests.
        codebase_link: Link to the source code repository.
        
    Returns:
        Formatted email body.
    """
    return f"""Hello,

Please find attached the automated ticket classification report.

Report Summary:
- Total tickets classified: {request_count}
- Classification method: LLM-based analysis against IT Service Catalog
- Report format: Microsoft Excel (.xlsx)

The attached report contains all classified IT helpdesk requests sorted by:
1. Request Category (ascending)
2. Request Type (ascending)
3. Short Description (ascending)

Source Code Repository:
{codebase_link}

This report was generated automatically by the Ticket Automation System.

Best regards,
Ticket Automation System
"""


def send_report_email(
    config: EmailConfig,
    report_path: Path,
    request_count: int,
) -> bool:
    """
    Send the classification report via email.
    
    Args:
        config: Email configuration.
        report_path: Path to the Excel report.
        request_count: Number of classified requests.
        
    Returns:
        True if sent successfully.
    """
    sender = SMTPEmailSender(config)
    
    subject = f"Automation Engineer interview - technical task - {config.sender_name}"
    body = build_report_email_body(request_count, config.codebase_link)
    
    return sender.send(
        to_email=config.recipient_email,
        subject=subject,
        body=body,
        attachments=[report_path],
    )
