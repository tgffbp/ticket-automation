# Automated Ticket Attribution System

An intelligent automation pipeline that classifies IT helpdesk requests against a Service Catalog using LLM-based analysis.

## 🎯 Overview

This system automates the classification of IT support tickets by:

1. **Data Ingestion**: Retrieves helpdesk requests from a webhook API and the Service Catalog from an external source
2. **LLM Classification**: Uses OpenAI's API to analyze each request and assign the appropriate category, request type, and SLA
3. **Report Generation**: Creates a formatted Microsoft Excel report with hierarchical sorting
4. **Email Delivery**: Sends the report to the specified recipient with attachments

## 🏗️ Architecture

```
ticket-automation/
├── src/
│   ├── __init__.py          # Package initialization
│   ├── config.py             # Configuration management (env vars)
│   ├── models.py             # Pydantic data models
│   ├── data_sources.py       # External API clients
│   ├── classifier.py         # LLM-based classification
│   ├── excel_generator.py    # Excel report generation
│   ├── email_sender.py       # Email sending (SMTP/SendGrid)
│   └── main.py               # CLI entry point & pipeline orchestration
├── requirements.txt          # Python dependencies
├── .env.example              # Environment variables template
├── .gitignore               # Git ignore rules
└── README.md                # This file
```

## 🚀 Quick Start

### Prerequisites

- Python 3.10 or higher
- OpenAI API key
- Email credentials (SMTP)

### Installation

```bash
# Clone the repository
git clone https://github.com/your-username/ticket-automation.git
cd ticket-automation

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy and configure environment variables
cp .env.example .env
# Edit .env with your actual credentials
```

### Configuration

Edit the `.env` file with your credentials:

```env
# Required
HELPDESK_API_KEY=my-cool-api-key
OPENAI_API_KEY=sk-your-openai-key

# Email (choose one provider)
EMAIL_PROVIDER=smtp
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=your-app-password
FROM_EMAIL=your-email@gmail.com

# Your info
SENDER_NAME=Your Name
CODEBASE_LINK=https://github.com/your-username/ticket-automation
```

### Running the Pipeline

```bash
# Run the complete pipeline
python -m src.main

# Run without sending email (for testing)
python -m src.main --skip-email

# Custom output path
python -m src.main --output ./my-report.xlsx

# Enable debug logging
python -m src.main --debug

# Validate configuration only
python -m src.main --validate-only
```

## 🔧 Configuration Options

All configuration is managed through environment variables. See `.env.example` for a complete list.

### Key Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `HELPDESK_API_KEY` | API key for helpdesk webhook | Required |
| `OPENAI_API_KEY` | OpenAI API key | Required |
| `LLM_MODEL` | Model for classification | `gpt-4o-mini` |
| `LLM_TEMPERATURE` | Classification temperature | `0.1` |
| `EMAIL_PROVIDER` | `smtp` or `sendgrid` | `smtp` |
| `SENDER_NAME` | Your name for email subject | Required |

## 📊 Output Format

The generated Excel report includes:

- **Formatted headers** (bold, colored)
- **Auto-fitted columns**
- **Alternating row colors** for readability
- **Hierarchical sorting**:
  1. Category (ascending)
  2. Request Type (ascending)
  3. Short Description (ascending)

### Columns

| Column | Description |
|--------|-------------|
| Request ID | Unique ticket identifier |
| Short Description | Brief issue summary |
| Long Description | Detailed description |
| Requester Email | Submitter's email |
| Category | Assigned service category |
| Request Type | Specific request type |
| SLA Value | SLA duration value |
| SLA Unit | SLA time unit (hours/days) |

## 🤖 Classification Logic

The LLM classifier uses a carefully crafted prompt that:

1. **Analyzes** the ticket's short and long descriptions
2. **Matches** against the Service Catalog categories and types
3. **Applies** priority rules for edge cases (e.g., security > hardware for lost devices)
4. **Provides** confidence scores and reasoning

### Service Categories

- Access Management
- Hardware Support
- Software & Licensing
- Network & Connectivity
- Security
- HR & Onboarding
- Other/Uncategorized

## 🔒 Security Considerations

This application follows security best practices:

- ✅ **No hardcoded secrets** - All credentials via environment variables
- ✅ **Secure defaults** - TLS enabled by default for SMTP
- ✅ **Input validation** - Pydantic models validate all data
- ✅ **Error handling** - No sensitive data in error messages
- ✅ **Git security** - `.env` and credentials excluded via `.gitignore`

### Gmail App Password

For Gmail SMTP, you need to use an App Password:
1. Enable 2-Factor Authentication on your Google account
2. Go to https://myaccount.google.com/apppasswords
3. Generate a new App Password for "Mail"
4. Use this password in `SMTP_PASSWORD`

## 📧 Email Providers

### SMTP (Gmail, Outlook, etc.)

```env
EMAIL_PROVIDER=smtp
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=your-app-password
```

### SendGrid

```env
EMAIL_PROVIDER=sendgrid
SENDGRID_API_KEY=SG.your-api-key
```

## 🧪 Development

### Project Structure

- **config.py**: Immutable dataclass configuration with validation
- **models.py**: Pydantic models for type safety and serialization
- **data_sources.py**: HTTP clients with context managers and error handling
- **classifier.py**: OpenAI integration with structured output and retries
- **excel_generator.py**: openpyxl-based report generation with styling
- **email_sender.py**: Strategy pattern for multiple email providers
- **main.py**: Click CLI with pipeline orchestration

### Error Handling

Each module defines specific exception classes:
- `DataSourceError` for API issues
- `ClassificationError` for LLM failures
- `ExcelGeneratorError` for report generation
- `EmailSenderError` for email delivery
- `PipelineError` for orchestration failures

## 📝 License

MIT License

## 👤 Author

Automation Engineer Technical Task Submission

