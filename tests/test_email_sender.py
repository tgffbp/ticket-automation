"""Tests for email sender module."""

import pytest
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory
from unittest.mock import Mock, patch, MagicMock

from src.config import EmailConfig
from src.email_sender import (
    SMTPEmailSender,
    EmailSenderError,
    build_report_email_body,
    send_report_email,
)


class TestSMTPEmailSender:
    """Tests for SMTPEmailSender."""
    
    @pytest.fixture
    def config(self):
        """Create test email config."""
        return EmailConfig(
            smtp_host="smtp.test.com",
            smtp_port=587,
            smtp_username="test@test.com",
            smtp_password="test-password",
            smtp_use_tls=True,
            from_email="sender@test.com",
            from_name="Test Sender",
            recipient_email="recipient@test.com",
            codebase_link="https://github.com/test",
            sender_name="Test User",
        )
    
    def test_init(self, config):
        """Test sender initialization."""
        sender = SMTPEmailSender(config)
        assert sender._config == config
    
    @patch("src.email_sender.smtplib.SMTP")
    def test_send_success(self, mock_smtp, config):
        """Test successful email sending."""
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__ = Mock(return_value=mock_server)
        mock_smtp.return_value.__exit__ = Mock(return_value=False)
        
        sender = SMTPEmailSender(config)
        result = sender.send(
            to_email="recipient@test.com",
            subject="Test Subject",
            body="Test body",
        )
        
        assert result is True
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once_with("test@test.com", "test-password")
        mock_server.send_message.assert_called_once()
    
    @patch("src.email_sender.smtplib.SMTP")
    def test_send_with_attachment(self, mock_smtp, config):
        """Test sending with attachment."""
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__ = Mock(return_value=mock_server)
        mock_smtp.return_value.__exit__ = Mock(return_value=False)
        
        with NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
            f.write(b"test content")
            temp_path = Path(f.name)
        
        try:
            sender = SMTPEmailSender(config)
            result = sender.send(
                to_email="recipient@test.com",
                subject="Test Subject",
                body="Test body",
                attachments=[temp_path],
            )
            
            assert result is True
        finally:
            temp_path.unlink()
    
    def test_send_attachment_not_found(self, config):
        """Test error when attachment doesn't exist."""
        sender = SMTPEmailSender(config)
        
        with pytest.raises(EmailSenderError, match="not found"):
            sender.send(
                to_email="recipient@test.com",
                subject="Test",
                body="Test",
                attachments=[Path("/nonexistent/file.xlsx")],
            )
    
    @patch("src.email_sender.smtplib.SMTP")
    def test_send_auth_error(self, mock_smtp, config):
        """Test authentication error handling."""
        import smtplib
        
        mock_server = MagicMock()
        mock_server.login.side_effect = smtplib.SMTPAuthenticationError(535, b"Auth failed")
        mock_smtp.return_value.__enter__ = Mock(return_value=mock_server)
        mock_smtp.return_value.__exit__ = Mock(return_value=False)
        
        sender = SMTPEmailSender(config)
        
        with pytest.raises(EmailSenderError, match="authentication failed"):
            sender.send(
                to_email="recipient@test.com",
                subject="Test",
                body="Test",
            )


class TestBuildReportEmailBody:
    """Tests for email body builder."""
    
    def test_contains_request_count(self):
        """Test body contains request count."""
        body = build_report_email_body(42, "https://github.com/test")
        assert "42" in body
    
    def test_contains_codebase_link(self):
        """Test body contains codebase link."""
        link = "https://github.com/test/repo"
        body = build_report_email_body(10, link)
        assert link in body
    
    def test_contains_sorting_info(self):
        """Test body explains sorting order."""
        body = build_report_email_body(10, "https://test.com")
        assert "Category" in body
        assert "ascending" in body.lower()


class TestSendReportEmail:
    """Tests for send_report_email function."""
    
    @patch("src.email_sender.SMTPEmailSender")
    def test_send_report_email(self, mock_sender_class):
        """Test send_report_email function."""
        mock_sender = MagicMock()
        mock_sender.send.return_value = True
        mock_sender_class.return_value = mock_sender
        
        config = EmailConfig(
            smtp_username="test@test.com",
            smtp_password="password",
            from_email="test@test.com",
            sender_name="Test User",
            codebase_link="https://github.com/test",
            recipient_email="recipient@test.com",
        )
        
        with TemporaryDirectory() as tmpdir:
            report_path = Path(tmpdir) / "report.xlsx"
            report_path.write_bytes(b"test")
            
            result = send_report_email(config, report_path, 42)
        
        assert result is True
        mock_sender.send.assert_called_once()
        
        # Check subject format
        call_args = mock_sender.send.call_args
        assert "Test User" in call_args.kwargs["subject"]
        assert "technical task" in call_args.kwargs["subject"]

