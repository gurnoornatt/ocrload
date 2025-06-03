# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Environment Setup
```bash
# Install dependencies
poetry install

# Run development server
poetry run uvicorn app.main:app --reload
```

### Testing
```bash
# Run all tests
poetry run pytest

# Run with coverage
poetry run pytest --cov=app

# Run specific test file
poetry run pytest tests/test_*.py -v

# Run integration tests only
poetry run pytest -m integration

# Run excluding slow tests
poetry run pytest -m "not slow"
```

### Code Quality
```bash
# Format code
poetry run black app tests

# Lint code  
poetry run ruff check app tests

# Fix linting issues
poetry run ruff check app tests --fix

# Type checking
poetry run mypy app
```

### Docker Operations
```bash
# Build production image
docker build -t ocr-docs-service .

# Run with environment file
docker run -p 8000:8000 --env-file .env ocr-docs-service

# Run development stack with Redis
docker-compose --profile dev up
```

## Architecture Overview

### Document Processing Pipeline
The system processes transportation documents (BOL, invoices, lumper receipts, etc.) through a semantic reasoning pipeline:

1. **File Upload** → `document_storage.py` (Supabase Storage)
2. **Document Registration** → `document_service.py` (PostgreSQL records)
3. **Document Conversion** → Datalab Marker API (converts to markdown)
4. **Semantic Analysis** → Claude Sonnet 3.5 (intelligent field extraction and reasoning)
5. **Structured Parsing** → `enhanced_*_parser.py` (validation and formatting)
6. **Event Emission** → `redis_event_service.py` (invoice readiness notifications)

### Service Architecture
- **Core Services**: `document_service.py`, `document_storage.py`, `supabase_client.py`
- **Document Conversion**: Datalab Marker API for markdown conversion
- **AI Processing**: Claude Sonnet 3.5 for semantic reasoning and field extraction
- **Infrastructure**: Performance monitoring, Redis events, database flag management

### Document Types Supported
- Bills of Lading (BOL) - shipping documentation
- Invoices - freight billing with line items and totals
- Lumper receipts - loading/unloading labor charges  
- Accessorial charges - detention, fuel, extra services
- Delivery confirmations and proof of delivery (POD)
- Packing lists - item descriptions, quantities, weights, SKUs

## Key Design Patterns

### Semantic Processing Strategy
- **Document Conversion**: Datalab Marker API converts images/PDFs to structured markdown
- **AI Reasoning**: Claude Sonnet 3.5 performs semantic analysis on markdown content
- **Enhanced Parsers** (`enhanced_*_parser.py`) - AI-powered field extraction with confidence scoring

### Processing Chain
1. **Primary**: Datalab Marker API for document-to-markdown conversion
2. **AI Analysis**: Claude Sonnet 3.5 for semantic understanding and field extraction
3. **Validation**: Confidence scoring and error handling

### Performance Requirements
- **Processing Turnaround**: ≤3s median processing time
- **Parse Success Rate**: ≥95% accuracy target (80%+ for delivery notes/packing lists)
- **Error Rate**: <1% 5xx errors
- Comprehensive monitoring via `performance_monitor.py`

## Testing Strategy

### Test Types
- **Unit Tests** (`tests/unit/`) - Individual component testing
- **Integration Tests** (`tests/integration/`) - Service interaction testing
- **Real Document Tests** (`tests/real/`) - Production accuracy validation

### Test Document Structure
```
test_documents/
├── bol/          # Bill of lading samples
├── invoices/     # Invoice samples  
├── lumper/       # Lumper receipt samples
├── accessorial/  # Detention and accessorial samples
├── delivery_note/ # POD and delivery confirmation samples
└── packing_list/ # Packing list samples
```

## Database Integration

### Supabase Tables
- **documents**: Processing results, metadata, confidence scores
- **drivers**: Driver information with doc_flags for verification
- **loads**: Load information with status updates

### Environment Variables Required
- `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` - Database access
- `DATALAB_API_KEY` - Document conversion service
- `CLAUDE_API_KEY` - AI semantic reasoning
- `REDIS_URL`, `REDIS_TOKEN` - Event system (Upstash)

## Current Task Status

### Active Development (Task 31)
Currently implementing delivery note & packing list parsers with 80%+ confidence targeting.

### Next Logical Tasks
Following task sequence: 41 → 43 → 44 → 33 → 38 → 34 → 35 → 45 → 36

### High Priority (Task 41)
Load document matching system for grouping related freight documents using extracted identifiers and address validation.

## Common Workflows

### Adding New Document Parser
1. Create enhanced parser in `app/services/enhanced_*_parser.py`
2. Update `DocumentType` enum in `app/models/database.py`
3. Add test documents in appropriate `test_documents/` subdirectory
4. Create integration tests in `tests/integration/`

### Testing with Real Documents
Use existing test documents in `test_documents/` subdirectories for validation against actual freight industry document formats.

### Performance Analysis
Use performance test files to validate processing speed and accuracy against targets.