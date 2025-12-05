"""Tests for configuration module."""

import os
import pytest
from unittest.mock import patch

from src.config import (
    APIConfig,
    LLMConfig,
    EmailConfig,
    OutputConfig,
    AppConfig,
    get_config,
)


class TestAPIConfig:
    """Tests for APIConfig."""
    
    def test_default_values(self):
        """Test default configuration values."""
        with patch.dict(os.environ, {}, clear=True):
            config = APIConfig()
            assert "anler.tech" in config.helpdesk_webhook_url
            assert config.request_timeout == 30
    
    def test_env_override(self):
        """Test environment variable override."""
        with patch.dict(os.environ, {"HELPDESK_API_KEY": "test-key"}):
            config = APIConfig()
            assert config.helpdesk_api_key == "test-key"


class TestLLMConfig:
    """Tests for LLMConfig."""
    
    def test_default_model(self):
        """Test default model is set."""
        config = LLMConfig()
        assert config.model == "gpt-4o-mini"
    
    def test_default_temperature(self):
        """Test default temperature for deterministic output."""
        config = LLMConfig()
        assert config.temperature == 0.1


class TestEmailConfig:
    """Tests for EmailConfig."""
    
    def test_default_smtp_settings(self):
        """Test default Gmail SMTP settings."""
        config = EmailConfig()
        assert config.smtp_host == "smtp.gmail.com"
        assert config.smtp_port == 587
        assert config.smtp_use_tls is True
    
    def test_default_recipient(self):
        """Test default recipient from task."""
        config = EmailConfig()
        assert config.recipient_email == "wordlessframes@gmail.com"


class TestOutputConfig:
    """Tests for OutputConfig."""
    
    def test_report_path(self):
        """Test report path property."""
        config = OutputConfig()
        assert config.report_path.name == "classified_tickets_report.xlsx"


class TestAppConfig:
    """Tests for AppConfig."""
    
    def test_validate_missing_api_key(self):
        """Test validation catches missing API key."""
        with patch.dict(os.environ, {"HELPDESK_API_KEY": ""}, clear=False):
            config = AppConfig(
                api=APIConfig(helpdesk_api_key=""),
            )
            errors = config.validate()
            assert any("HELPDESK_API_KEY" in e for e in errors)
    
    def test_validate_missing_openai_key(self):
        """Test validation catches missing OpenAI key."""
        config = AppConfig(
            api=APIConfig(helpdesk_api_key="test"),
            llm=LLMConfig(api_key=""),
        )
        errors = config.validate()
        assert any("OPENAI_API_KEY" in e for e in errors)
    
    def test_validate_missing_smtp_password(self):
        """Test validation catches missing SMTP password."""
        config = AppConfig(
            api=APIConfig(helpdesk_api_key="test"),
            llm=LLMConfig(api_key="test"),
            email=EmailConfig(
                smtp_username="test@gmail.com",
                smtp_password="",
            ),
        )
        errors = config.validate()
        assert any("SMTP_PASSWORD" in e for e in errors)
    
    def test_validate_all_valid(self):
        """Test validation passes with all required fields."""
        config = AppConfig(
            api=APIConfig(helpdesk_api_key="test"),
            llm=LLMConfig(api_key="sk-test"),
            email=EmailConfig(
                smtp_username="test@gmail.com",
                smtp_password="app-password",
                from_email="test@gmail.com",
                sender_name="Test User",
            ),
        )
        errors = config.validate()
        assert len(errors) == 0


class TestGetConfig:
    """Tests for get_config function."""
    
    def test_returns_app_config(self):
        """Test get_config returns AppConfig instance."""
        config = get_config()
        assert isinstance(config, AppConfig)

