# Document Storage Service

The Document Storage Service handles downloading, validating, and uploading files to Supabase Storage with comprehensive error handling and validation.

## Features

- **File Download**: Download files from URLs (e.g., WhatsApp media URLs)
- **Local File Reading**: Read and process local files 
- **File Validation**: Validate file types, sizes, and content
- **Storage Upload**: Upload to Supabase Storage with organized folder structure
- **Error Handling**: Comprehensive error handling with specific exceptions

## File Validation

### Supported File Types
- **Images**: `.jpg`, `.jpeg`, `.png`
- **Documents**: `.pdf`

### File Size Limits
- Maximum file size: 10MB
- Minimum file size: 1 byte

### MIME Type Validation
- `image/jpeg`, `image/jpg`, `image/png`
- `application/pdf`

## Storage Organization

Files are stored in Supabase Storage with the following structure:
```
{driver_id}/{doc_type}/{timestamp}_{filename}
```

Example:
```
550e8400-e29b-41d4-a716-446655440000/CDL/20240115_120000_license.jpg
```

## Usage Examples

### Download and Upload from URL

```python
from app.services.document_storage import document_storage_service
from uuid import uuid4

# Download, validate, and upload file from URL
driver_id = uuid4()
media_url = "https://api.whatsapp.com/v1/media/abc123"

try:
    result = await document_storage_service.process_url_upload(
        media_url=media_url,
        driver_id=driver_id,
        doc_type="CDL"
    )
    
    print(f"File uploaded: {result['public_url']}")
    print(f"Original filename: {result['original_filename']}")
    print(f"File size: {result['file_size']} bytes")
    print(f"Content type: {result['content_type']}")
    
except FileValidationError as e:
    print(f"File validation failed: {e}")
except DownloadError as e:
    print(f"Download failed: {e}")
except StorageError as e:
    print(f"Storage upload failed: {e}")
```

### Upload Local File

```python
# Upload local file
file_path = "/path/to/local/document.pdf"

try:
    result = await document_storage_service.process_local_upload(
        file_path=file_path,
        driver_id=driver_id,
        doc_type="COI"
    )
    
    print(f"Local file uploaded: {result['public_url']}")
    
except FileValidationError as e:
    print(f"File validation failed: {e}")
except DownloadError as e:
    print(f"File reading failed: {e}")
except StorageError as e:
    print(f"Storage upload failed: {e}")
```

### Manual Process Steps

```python
# Step-by-step process for custom workflows

# 1. Download file
try:
    file_content, filename, content_type = await document_storage_service.download_file_from_url(
        "https://example.com/document.jpg"
    )
except (DownloadError, FileValidationError) as e:
    print(f"Download failed: {e}")
    return

# 2. Upload to storage
try:
    public_url = await document_storage_service.upload_to_storage(
        file_content=file_content,
        driver_id=driver_id,
        doc_type="CDL",
        original_filename=filename,
        content_type=content_type
    )
    print(f"Uploaded to: {public_url}")
except StorageError as e:
    print(f"Upload failed: {e}")
```

## Error Handling

### Exception Types

- **`FileValidationError`**: File doesn't meet validation criteria
  - Invalid file type/extension
  - File too large or too small
  - Unsupported MIME type

- **`DownloadError`**: File download/reading failed
  - Network errors
  - HTTP errors (404, 500, etc.)
  - File not found
  - Timeout errors

- **`StorageError`**: Storage upload failed
  - Supabase Storage errors
  - Authentication/authorization issues
  - Network connectivity to storage

### Example Error Handling

```python
try:
    result = await document_storage_service.process_url_upload(
        media_url="https://api.whatsapp.com/media/123",
        driver_id=uuid4(),
        doc_type="CDL"
    )
except FileValidationError as e:
    # Handle validation errors
    if "file type" in str(e).lower():
        return {"error": "unsupported_file_type", "message": str(e)}
    elif "file size" in str(e).lower():
        return {"error": "file_too_large", "message": str(e)}
    else:
        return {"error": "validation_failed", "message": str(e)}
        
except DownloadError as e:
    # Handle download errors
    if "HTTP 404" in str(e):
        return {"error": "file_not_found", "message": "File not found"}
    elif "timeout" in str(e).lower():
        return {"error": "download_timeout", "message": "Download timed out"}
    else:
        return {"error": "download_failed", "message": str(e)}
        
except StorageError as e:
    # Handle storage errors
    return {"error": "storage_failed", "message": "Failed to save file"}
```

## Integration with Database Models

```python
from app.models.database import Document, DocumentType
from app.services.document_storage import document_storage_service
from app.services.supabase_client import supabase_service

async def process_document_upload(driver_id: UUID, media_url: str, doc_type: str):
    """Complete document processing workflow."""
    
    # Upload file
    upload_result = await document_storage_service.process_url_upload(
        media_url=media_url,
        driver_id=driver_id,
        doc_type=doc_type
    )
    
    # Create database record
    document = Document(
        driver_id=driver_id,
        type=DocumentType(doc_type),
        url=upload_result["public_url"],
        original_filename=upload_result["original_filename"],
        file_size=upload_result["file_size"],
        content_type=upload_result["content_type"]
    )
    
    # Save to database
    saved_document = await supabase_service.create_document(document)
    
    return {
        "document_id": saved_document.id,
        "public_url": upload_result["public_url"],
        "ready_for_ocr": True
    }
```

## Configuration

The service uses the following configuration:

- **Session Timeout**: 60 seconds total, 10 seconds connect, 30 seconds read
- **User Agent**: `OCR-Load-Service/1.0`
- **Storage Integration**: Uses `supabase_service` for uploads
- **Chunk Size**: 8192 bytes for streaming downloads

## Session Management

The service automatically manages HTTP sessions:
- Creates sessions on-demand with appropriate timeouts
- Reuses sessions for multiple requests
- Properly closes sessions when service is closed

```python
# Manually close session when done (optional)
await document_storage_service.close()
```

## Testing

The service includes comprehensive unit tests covering:
- File validation (types, sizes, MIME types)
- Download scenarios (success, errors, timeouts)
- Local file reading
- Storage upload integration
- Error handling paths

Run tests with:
```bash
python -m pytest tests/test_document_storage.py -v
``` 