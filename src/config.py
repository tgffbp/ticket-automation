"""
Configuration module for the Ticket Automation System.

Handles all configuration through environment variables with secure defaults.
Never stores sensitive data directly in code.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


# Load environment variables from .env file
load_dotenv()


@dataclass(frozen=True)
class APIConfig:
    """Configuration for external API endpoints."""
    
    # Helpdesk API configuration
    helpdesk_webhook_url: str = field(
        default_factory=lambda: os.getenv("HELPDESK_WEBHOOK_URL", "")
    )
    helpdesk_api_key: str = field(
        default_factory=lambda: os.getenv("HELPDESK_API_KEY", "")
    )
    helpdesk_api_secret: str = field(
        default_factory=lambda: os.getenv("HELPDESK_API_SECRET", "")
    )
    
    # Service Catalog URL
    service_catalog_url: str = field(
        default_factory=lambda: os.getenv("SERVICE_CATALOG_URL", "")
    )
    
    # Request timeout in seconds
    request_timeout: int = field(
        default_factory=lambda: int(os.getenv("REQUEST_TIMEOUT", "30"))
    )


@dataclass(frozen=True)
class LLMConfig:
    """Configuration for LLM API (OpenAI compatible)."""
    
    api_key: str = field(
        default_factory=lambda: os.getenv("OPENAI_API_KEY", "")
    )
    api_base_url: Optional[str] = field(
        default_factory=lambda: os.getenv("OPENAI_API_BASE", None)
    )
    model: str = field(
        default_factory=lambda: os.getenv("LLM_MODEL", "gpt-4o-mini")
    )
    temperature: float = field(
        default_factory=lambda: float(os.getenv("LLM_TEMPERATURE", "0.1"))
    )
    max_tokens: int = field(
        default_factory=lambda: int(os.getenv("LLM_MAX_TOKENS", "500"))
    )
    max_retries: int = field(
        default_factory=lambda: int(os.getenv("LLM_MAX_RETRIES", "3"))
    )


@dataclass(frozen=True)
class EmailConfig:
    """
    Configuration for email sending via SMTP.
    
    Designed for Gmail with App Password authentication.
    """
    
    # SMTP settings
    smtp_host: str = field(
        default_factory=lambda: os.getenv("SMTP_HOST", "smtp.gmail.com")
    )
    smtp_port: int = field(
        default_factory=lambda: int(os.getenv("SMTP_PORT", "587"))
    )
    smtp_username: str = field(
        default_factory=lambda: os.getenv("SMTP_USERNAME", "")
    )
    smtp_password: str = field(
        default_factory=lambda: os.getenv("SMTP_PASSWORD", "")
    )
    smtp_use_tls: bool = field(
        default_factory=lambda: os.getenv("SMTP_USE_TLS", "true").lower() == "true"
    )
    
    # Sender settings
    from_email: str = field(
        default_factory=lambda: os.getenv("FROM_EMAIL", "")
    )
    from_name: str = field(
        default_factory=lambda: os.getenv("FROM_NAME", "Ticket Automation System")
    )
    
    # Recipient for the report
    recipient_email: str = field(
        default_factory=lambda: os.getenv("RECIPIENT_EMAIL", "")
    )
    
    # Link to codebase for the email
    codebase_link: str = field(
        default_factory=lambda: os.getenv("CODEBASE_LINK", "")
    )
    
    # Sender's name for the subject
    sender_name: str = field(
        default_factory=lambda: os.getenv("SENDER_NAME", "")
    )


@dataclass(frozen=True)
class OutputConfig:
    """Configuration for output files."""
    
    output_dir: Path = field(
        default_factory=lambda: Path(os.getenv("OUTPUT_DIR", "./output"))
    )
    report_filename: str = field(
        default_factory=lambda: os.getenv(
            "REPORT_FILENAME", 
            "classified_tickets_report.xlsx"
        )
    )
    
    @property
    def report_path(self) -> Path:
        """Get full path to the report file."""
        return self.output_dir / self.report_filename


@dataclass(frozen=True)
class AppConfig:
    """Main application configuration aggregating all config sections."""
    
    api: APIConfig = field(default_factory=APIConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    email: EmailConfig = field(default_factory=EmailConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    
    # Logging level
    log_level: str = field(
        default_factory=lambda: os.getenv("LOG_LEVEL", "INFO")
    )
    
    # Batch size for LLM requests (to avoid rate limits)
    classification_batch_size: int = field(
        default_factory=lambda: int(os.getenv("CLASSIFICATION_BATCH_SIZE", "5"))
    )
    
    def validate(self) -> list[str]:
        """
        Validate configuration and return list of errors.
        
        Returns:
            List of validation error messages (empty if valid).
        """
        errors = []
        
        # Validate required API endpoints
        if not self.api.helpdesk_webhook_url:
            errors.append("HELPDESK_WEBHOOK_URL is required")
        if not self.api.service_catalog_url:
            errors.append("SERVICE_CATALOG_URL is required")
        if not self.api.helpdesk_api_key:
            errors.append("HELPDESK_API_KEY is required")
        
        # Validate LLM configuration
        if not self.llm.api_key:
            errors.append("OPENAI_API_KEY is required for classification")
        
        # Validate email configuration
        if not self.email.smtp_username:
            errors.append("SMTP_USERNAME is required")
        if not self.email.smtp_password:
            errors.append("SMTP_PASSWORD (App Password) is required")
        if not self.email.from_email:
            errors.append("FROM_EMAIL is required for sending emails")
        if not self.email.recipient_email:
            errors.append("RECIPIENT_EMAIL is required")
        if not self.email.sender_name:
            errors.append("SENDER_NAME is required for email subject")
        
        return errors


def get_config() -> AppConfig:
    """
    Get application configuration singleton.
    
    Returns:
        AppConfig instance with all settings loaded from environment.
    """
    return AppConfig()

