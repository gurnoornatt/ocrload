# OCR & Docs Micro-Service

FastAPI micro-service for OCR processing of transportation documents with Supabase integration and Railway deployment.

## Features

- **Document Processing**: CDL, COI, Agreement, Rate Confirmation, and POD documents
- **OCR Integration**: Primary Datalab.to API with Marker API fallback
- **Database**: Supabase PostgreSQL with automatic flag updates
- **Storage**: Supabase Storage for document files
- **Events**: Redis-based event system for invoice_ready notifications
- **Deployment**: Docker containerization with Railway deployment

## Tech Stack

- **Backend**: FastAPI 0.104+ with Python 3.12
- **Database**: Supabase (PostgreSQL + Storage)
- **OCR APIs**: Datalab.to (primary), Marker (fallback)
- **Event Bus**: Redis (Upstash compatible)
- **Testing**: pytest with async support
- **Code Quality**: ruff, black, mypy
- **Deployment**: Docker + Railway

## Quick Start

1. **Install Poetry** (if not already installed):
   ```bash
   curl -sSL https://install.python-poetry.org | python3 -
   export PATH="$HOME/.local/bin:$PATH"
   ```

2. **Install Dependencies**:
   ```bash
   poetry install
   ```

3. **Set Environment Variables**:
   ```bash
   cp .env.example .env
   # Edit .env with your actual API keys
   ```

4. **Run Development Server**:
   ```bash
   poetry run uvicorn app.main:app --reload
   ```

## API Endpoints

### Health Check
- `GET /health` - Service health status

### Document Processing
- `POST /api/media` - Process document from WhatsApp media URL
- `POST /api/parse-test` - Process local file for testing

## Environment Variables

```bash
# Supabase Configuration
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your_anon_key
SUPABASE_SERVICE_KEY=your_service_key

# OCR API Configuration
DATALAB_API_KEY=your_datalab_key
MARKER_API_KEY=your_marker_key

# Storage Configuration
AWS_REGION=us-east-1
S3_BUCKET=raw_docs

# Redis Configuration
REDIS_URL=redis://localhost:6379

# Optional
OPENAI_API_KEY=your_openai_key
```

## Testing

```bash
# Run all tests
poetry run pytest

# Run with coverage
poetry run pytest --cov=app

# Run specific test
poetry run pytest tests/test_parsers.py -v
```

## Code Quality

```bash
# Format code
poetry run black app tests

# Lint code
poetry run ruff check app tests

# Type checking
poetry run mypy app
```

## Docker

```bash
# Build image
docker build -t ocr-docs-service .

# Run container
docker run -p 8000:8000 --env-file .env ocr-docs-service
```

## Development Workflow

1. Create feature branch
2. Implement changes with tests
3. Run code quality checks
4. Submit pull request
5. CI/CD pipeline runs automatically
6. Deploy to Railway on merge

## Performance Requirements

- **OCR Turnaround**: ≤3s median
- **Parse Success Rate**: ≥95%
- **Error Rate**: <1% 5xx errors

## Database Schema

The service interacts with existing Supabase tables:
- `documents`: Stores OCR results and metadata
- `drivers`: Driver information with doc_flags for verification
- `loads`: Load information with status updates

## License

MIT License - see LICENSE file for details 