# Services Module

This module contains service classes for interacting with external systems and databases.

## Supabase Client Service

The `SupabaseService` class provides a comprehensive interface for interacting with Supabase database and storage.

### Features

- **Database Operations**: CRUD operations for drivers, loads, documents, and transactions
- **Storage Operations**: File upload, download, and management
- **Health Monitoring**: Connection health checks for monitoring
- **Error Handling**: Graceful handling of permission errors and connection issues
- **Flexible Authentication**: Supports both service key and anon key authentication

### Configuration

The service uses settings from `app.config.settings`:

```python
# Required
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-anon-key

# Optional (for admin operations)
SUPABASE_SERVICE_KEY=your-service-key

# Storage bucket name
S3_BUCKET=raw_docs
```

### Usage

```python
from app.services.supabase_client import supabase_service

# Database operations
driver = await supabase_service.get_driver_by_id("driver-uuid")
document = await supabase_service.create_document({
    "driver_id": "driver-uuid",
    "type": "CDL",
    "url": "https://storage.url/file.jpg",
    "confidence": 0.95
})

# Storage operations
public_url = await supabase_service.upload_file(
    "documents/file.jpg", 
    file_content, 
    "image/jpeg"
)

# Health checks
health = await supabase_service.health_check()
```

### Database Schema

The service works with the existing database schema:

#### Tables
- `drivers`: Driver information and document flags
- `loads`: Load/shipment information
- `documents`: OCR processed documents
- `transactions`: Transaction records

#### Key Columns
- `drivers.doc_flags`: JSONB column for document verification flags
- `documents.type`: Document type (CDL, COI, AGREEMENT, RATE_CON, POD)
- `documents.confidence`: OCR confidence score (0.0-1.0)
- `documents.parsed_data`: JSONB column for extracted data

### Health Check Statuses

The health check returns different status levels:

- **healthy**: Full functionality available
- **limited**: Database accessible but with restricted permissions (anon key)
- **warning**: Non-critical issues (e.g., missing storage bucket)
- **unhealthy**: Critical failures requiring attention

### Error Handling

The service handles various error scenarios:

- **Permission Errors**: Gracefully handles anon key limitations
- **Connection Failures**: Provides detailed error messages
- **Missing Resources**: Handles missing buckets or tables
- **API Errors**: Logs and re-raises Supabase API errors

### Testing

- Unit tests: Mock all external dependencies
- Integration tests: Test against real Supabase instance
- Health tests: Verify endpoint responses and status codes

```bash
# Run unit tests
pytest tests/test_supabase_client.py -v

# Run integration tests (requires credentials)
pytest tests/test_supabase_integration.py -v -m integration

# Run health endpoint tests
pytest tests/test_health.py -v
``` 