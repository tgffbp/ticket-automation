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
│   ├── email_sender.py       # SMTP email sending
│   └── main.py               # CLI entry point & pipeline orchestration
├── tests/                    # Unit tests
├── requirements.txt          # Python dependencies
├── pyproject.toml           # Project configuration
├── .env.example              # Environment variables template
├── .gitignore               # Git ignore rules
└── README.md                # This file
```

## 🚀 Quick Start

### Prerequisites

- Python 3.10 or higher
- OpenAI API key
- Gmail account with App Password

### Installation

```bash
# Clone the repository
git clone <repository-url>
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
# Required - Helpdesk API
HELPDESK_API_KEY=my-cool-api-key
HELPDESK_API_SECRET=<your-api-secret>

# Required - OpenAI
OPENAI_API_KEY=sk-your-openai-key

# Required - Email (Gmail + App Password)
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=xxxx-xxxx-xxxx-xxxx
FROM_EMAIL=your-email@gmail.com

# Required - Your info for the email
SENDER_NAME=Your Name
CODEBASE_LINK=https://github.com/your-username/ticket-automation
```

### Running the Pipeline

```bash
# Run the complete pipeline (classify + generate report + send email)
python -m src.main

# Run without sending email (for testing)
python -m src.main --skip-email

# Custom output path
python -m src.main --output ./my-report.xlsx

# Enable debug logging
python -m src.main --debug

# Validate configuration only (no execution)
python -m src.main --validate-only
```

### Example Output

```
2025-12-05 15:30:00 | INFO | ============================================================
2025-12-05 15:30:00 | INFO | Starting Ticket Automation Pipeline
2025-12-05 15:30:00 | INFO | ============================================================
2025-12-05 15:30:00 | INFO | Step 1: Fetching data from external sources
2025-12-05 15:30:01 | INFO | Successfully fetched 42 helpdesk requests
2025-12-05 15:30:02 | INFO | Parsed catalog: 7 categories, 22 request types
2025-12-05 15:30:02 | INFO | Step 2: Classifying requests using LLM
2025-12-05 15:30:02 | INFO | Starting classification of 42 requests
2025-12-05 15:30:15 | INFO | Progress: 5/42 requests classified
...
2025-12-05 15:32:00 | INFO | Classification complete: 42 requests processed
2025-12-05 15:32:00 | INFO | Step 3: Generating Excel report
2025-12-05 15:32:01 | INFO | Report generated: output/classified_tickets_report.xlsx
2025-12-05 15:32:01 | INFO | Step 4: Sending report via email
2025-12-05 15:32:03 | INFO | Email sent to: recipient@example.com
2025-12-05 15:32:03 | INFO | ============================================================
2025-12-05 15:32:03 | INFO | Pipeline completed successfully!
2025-12-05 15:32:03 | INFO | ============================================================
```

## 🧪 Testing

```bash
# Run all tests
python -m pytest tests/ -v

# Run with coverage report
python -m pytest tests/ -v --cov=src --cov-report=term-missing

# Run specific test file
python -m pytest tests/test_models.py -v
```

Current test coverage: **60%** (45 tests)

## 🔧 Configuration Options

All configuration is managed through environment variables. See `.env.example` for a complete list.

### Key Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `HELPDESK_API_KEY` | API key for helpdesk webhook | Required |
| `HELPDESK_API_SECRET` | API secret for helpdesk webhook | Required |
| `OPENAI_API_KEY` | OpenAI API key | Required |
| `LLM_MODEL` | Model for classification | `gpt-4o-mini` |
| `LLM_TEMPERATURE` | Classification temperature (lower = more deterministic) | `0.1` |
| `SMTP_USERNAME` | Gmail address | Required |
| `SMTP_PASSWORD` | Gmail App Password | Required |
| `SENDER_NAME` | Your name for email subject | Required |

## 📊 Output Format

The generated Excel report includes:

- **Formatted headers** (bold, colored background)
- **Auto-fitted columns**
- **Alternating row colors** for readability
- **Frozen header row**
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
5. **Falls back** gracefully when catalog entries don't match exactly

### Service Categories

- Access Management
- Hardware Support
- Software & Licensing
- Network & Connectivity
- Security
- HR & Onboarding
- Other/Uncategorized

### Resilience Features

- **Fuzzy matching**: Handles slight variations in category names from LLM
- **Graceful degradation**: Unknown categories fall back to "Other/Uncategorized"
- **Forward compatibility**: Ignores unknown fields from API responses
- **Default SLA**: 24 hours when SLA lookup fails

## 🔒 Security Considerations

This application follows security best practices:

- ✅ **No hardcoded secrets** - All credentials via environment variables
- ✅ **Secure defaults** - TLS enabled by default for SMTP
- ✅ **Input validation** - Pydantic models validate all data
- ✅ **Error handling** - No sensitive data in error messages
- ✅ **Git security** - `.env` and credentials excluded via `.gitignore`

### Gmail App Password Setup

For Gmail SMTP, you need to use an App Password (not your regular password):

1. Enable 2-Factor Authentication on your Google account
2. Go to https://myaccount.google.com/apppasswords
3. Generate a new App Password for "Mail"
4. Use this 16-character password in `SMTP_PASSWORD`

## 📁 Project Structure

| Module | Purpose |
|--------|---------|
| `config.py` | Immutable dataclass configuration with validation |
| `models.py` | Pydantic models for type safety and serialization |
| `data_sources.py` | HTTP clients with context managers and error handling |
| `classifier.py` | OpenAI integration with structured output, retries, fuzzy matching |
| `excel_generator.py` | openpyxl-based report generation with professional styling |
| `email_sender.py` | SMTP email sending with TLS |
| `main.py` | Click CLI with pipeline orchestration |

### Error Handling

Each module defines specific exception classes:
- `DataSourceError` for API issues
- `ClassificationError` for LLM failures
- `ExcelGeneratorError` for report generation
- `EmailSenderError` for email delivery
- `PipelineError` for orchestration failures

## 📝 License

MIT License
