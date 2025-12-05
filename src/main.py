"""
Main entry point for the Ticket Automation System.

Orchestrates the complete pipeline:
1. Fetch helpdesk requests and service catalog
2. Classify requests using LLM
3. Generate Excel report
4. Send report via email
"""

import logging
import sys
from pathlib import Path
from typing import Optional

import click

from .config import get_config, AppConfig
from .data_sources import fetch_all_data, DataSourceError
from .classifier import TicketClassifier, ClassificationError
from .excel_generator import generate_report, ExcelGeneratorError
from .email_sender import send_report_email, EmailSenderError


def setup_logging(level: str) -> None:
    """
    Configure application logging.
    
    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR).
    """
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
    )
    
    # Reduce noise from third-party libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


logger = logging.getLogger(__name__)


class PipelineError(Exception):
    """Error during pipeline execution."""
    pass


def validate_config(config: AppConfig) -> None:
    """
    Validate configuration before running.
    
    Args:
        config: Application configuration.
        
    Raises:
        PipelineError: If configuration is invalid.
    """
    errors = config.validate()
    if errors:
        for error in errors:
            logger.error(f"Configuration error: {error}")
        raise PipelineError(
            f"Configuration validation failed with {len(errors)} error(s)"
        )


def run_pipeline(
    config: Optional[AppConfig] = None,
    skip_email: bool = False,
    output_path: Optional[Path] = None,
) -> Path:
    """
    Execute the complete ticket automation pipeline.
    
    Args:
        config: Optional configuration override.
        skip_email: If True, skip sending email.
        output_path: Optional custom output path for the report.
        
    Returns:
        Path to the generated report.
        
    Raises:
        PipelineError: If any step fails.
    """
    if config is None:
        config = get_config()
    
    # Override output path if provided
    if output_path:
        config = AppConfig(
            api=config.api,
            llm=config.llm,
            email=config.email,
            output=config.output.__class__(
                output_dir=output_path.parent,
                report_filename=output_path.name,
            ),
            log_level=config.log_level,
            classification_batch_size=config.classification_batch_size,
        )
    
    setup_logging(config.log_level)
    logger.info("=" * 60)
    logger.info("Starting Ticket Automation Pipeline")
    logger.info("=" * 60)
    
    # Validate configuration (skip email validation if not sending)
    if not skip_email:
        validate_config(config)
    else:
        # Validate only non-email config
        errors = []
        if not config.api.helpdesk_webhook_url:
            errors.append("HELPDESK_WEBHOOK_URL is required")
        if not config.api.service_catalog_url:
            errors.append("SERVICE_CATALOG_URL is required")
        if not config.api.helpdesk_api_key:
            errors.append("HELPDESK_API_KEY is required")
        if not config.llm.api_key:
            errors.append("OPENAI_API_KEY is required")
        if errors:
            for error in errors:
                logger.error(f"Configuration error: {error}")
            raise PipelineError(
                f"Configuration validation failed with {len(errors)} error(s)"
            )
    
    # Step 1: Fetch data
    logger.info("-" * 40)
    logger.info("Step 1: Fetching data from external sources")
    logger.info("-" * 40)
    
    try:
        requests, catalog = fetch_all_data(config.api)
        logger.info(f"Fetched {len(requests)} requests")
        logger.info(f"Catalog has {len(catalog.categories)} categories")
    except DataSourceError as e:
        raise PipelineError(f"Data fetch failed: {e}") from e
    
    # Step 2: Classify requests
    logger.info("-" * 40)
    logger.info("Step 2: Classifying requests using LLM")
    logger.info("-" * 40)
    
    try:
        classifier = TicketClassifier(config.llm, catalog)
        classified_requests = classifier.classify_batch(
            requests,
            batch_size=config.classification_batch_size,
        )
    except ClassificationError as e:
        raise PipelineError(f"Classification failed: {e}") from e
    
    # Step 3: Generate Excel report
    logger.info("-" * 40)
    logger.info("Step 3: Generating Excel report")
    logger.info("-" * 40)
    
    try:
        report_path = generate_report(classified_requests, config.output)
        logger.info(f"Report generated: {report_path}")
    except ExcelGeneratorError as e:
        raise PipelineError(f"Report generation failed: {e}") from e
    
    # Step 4: Send email (optional)
    if not skip_email:
        logger.info("-" * 40)
        logger.info("Step 4: Sending report via email")
        logger.info("-" * 40)
        
        try:
            send_report_email(
                config.email,
                report_path,
                len(classified_requests),
            )
            logger.info(f"Email sent to: {config.email.recipient_email}")
        except EmailSenderError as e:
            raise PipelineError(f"Email sending failed: {e}") from e
    else:
        logger.info("-" * 40)
        logger.info("Step 4: Skipping email (--skip-email flag)")
        logger.info("-" * 40)
    
    logger.info("=" * 60)
    logger.info("Pipeline completed successfully!")
    logger.info(f"Report saved to: {report_path}")
    logger.info("=" * 60)
    
    return report_path


@click.command()
@click.option(
    "--skip-email",
    is_flag=True,
    default=False,
    help="Skip sending the email (useful for testing)",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(dir_okay=False, path_type=Path),
    help="Custom output path for the report",
)
@click.option(
    "--debug",
    is_flag=True,
    default=False,
    help="Enable debug logging",
)
@click.option(
    "--validate-only",
    is_flag=True,
    default=False,
    help="Only validate configuration without running the pipeline",
)
def main(
    skip_email: bool,
    output: Optional[Path],
    debug: bool,
    validate_only: bool,
) -> None:
    """
    Automated Ticket Attribution System.
    
    Classifies IT helpdesk requests against a Service Catalog
    using LLM-based analysis and generates an Excel report.
    """
    try:
        config = get_config()
        
        if debug:
            config = AppConfig(
                api=config.api,
                llm=config.llm,
                email=config.email,
                output=config.output,
                log_level="DEBUG",
                classification_batch_size=config.classification_batch_size,
            )
        
        if validate_only:
            setup_logging(config.log_level)
            logger.info("Validating configuration...")
            validate_config(config)
            logger.info("Configuration is valid!")
            return
        
        run_pipeline(config, skip_email=skip_email, output_path=output)
        
    except PipelineError as e:
        click.echo(f"Pipeline failed: {e}", err=True)
        sys.exit(1)
    except KeyboardInterrupt:
        click.echo("\nOperation cancelled by user", err=True)
        sys.exit(130)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        if debug:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

