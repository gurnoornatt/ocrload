# OCR Clients

This module provides OCR (Optical Character Recognition) client implementations for processing documents and images.

## Datalab OCR Client

The `DatalabOCRClient` provides integration with [Datalab.to](https://www.datalab.to) OCR API, which offers high-quality text extraction from images and PDF documents.

### Features

- **Async Processing**: Submit requests and poll for results asynchronously
- **Multiple File Types**: Support for PDF, JPG, JPEG, PNG, WEBP, GIF, TIFF
- **Language Hints**: Optional language specification for better OCR accuracy
- **Rate Limiting**: Built-in rate limit handling (200 requests/minute)
- **Error Handling**: Comprehensive error handling with custom exceptions
- **Response Parsing**: Structured parsing of OCR results with confidence scores
- **File Validation**: Size and type validation before processing
- **Context Manager**: Proper session management and cleanup

### Configuration

Add your Datalab API key to the environment:

```bash
# In .env file
DATALAB_API_KEY=your-datalab-api-key-here
```

### Basic Usage

#### Processing File Content

```python
from app.services.ocr_clients import DatalabOCRClient

# Using context manager (recommended)
async with DatalabOCRClient() as client:
    result = await client.process_file_content(
        file_content=file_bytes,
        filename="document.pdf",
        mime_type="application/pdf",
        languages=["English", "Spanish"]  # Optional
    )
    
    print(f"Extracted text: {result['full_text']}")
    print(f"Confidence: {result['average_confidence']:.3f}")
    print(f"Pages: {result['page_count']}")
```

#### Processing Local Files

```python
async with DatalabOCRClient() as client:
    result = await client.process_file_path(
        file_path="/path/to/document.pdf",
        languages=["English"],
        max_pages=10  # Optional limit
    )
    
    # Access per-page results
    for page in result['pages']:
        print(f"Page {page['page_number']}: {page['text']}")
        print(f"Confidence: {page['average_confidence']:.3f}")
```

#### Using Global Client Instance

```python
from app.services.ocr_clients.datalab_client import datalab_ocr_client

# The global instance handles session management automatically
result = await datalab_ocr_client.process_file_content(
    file_content=file_bytes,
    filename="image.jpg",
    mime_type="image/jpeg"
)
```

### Response Format

The client returns a standardized response format:

```python
{
    'success': True,
    'page_count': 2,
    'full_text': 'Combined text from all pages',
    'average_confidence': 0.95,
    'pages': [
        {
            'page_number': 1,
            'text': 'Text from page 1',
            'average_confidence': 0.94,
            'text_lines': [
                {
                    'text': 'Individual line text',
                    'confidence': 0.98,
                    'bbox': [x1, y1, x2, y2],  # Bounding box
                    'polygon': [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
                }
            ],
            'languages': ['en'],
            'image_bbox': [0, 0, width, height]
        }
    ],
    'metadata': {
        'provider': 'datalab',
        'processing_time': 15.2,
        'total_text_lines': 45
    }
}
```

### Configuration Options

#### Client Initialization

```python
# Custom API key
client = DatalabOCRClient(api_key="custom-key")

# Use settings from environment (default)
client = DatalabOCRClient()
```

#### Processing Parameters

- **languages**: List of up to 4 language hints (e.g., ["English", "Spanish"])
- **max_pages**: Maximum number of pages to process
- **max_polls**: Maximum polling attempts (default: 300)
- **poll_interval**: Initial polling interval in seconds (default: 2)

### Error Handling

The client provides specific exceptions for different error conditions:

```python
from app.services.ocr_clients.datalab_client import (
    DatalabOCRError,
    DatalabAuthenticationError,
    DatalabRateLimitError,
    DatalabProcessingError,
    DatalabTimeoutError
)

try:
    result = await client.process_file_content(file_content, filename, mime_type)
except DatalabAuthenticationError:
    # Invalid API key
    print("Check your API key configuration")
except DatalabRateLimitError:
    # Rate limit exceeded
    print("Too many requests, wait before retrying")
except DatalabProcessingError as e:
    # OCR processing failed
    print(f"Processing error: {e}")
except DatalabTimeoutError:
    # Request timed out
    print("Request took too long to complete")
except DatalabOCRError as e:
    # General OCR error
    print(f"OCR error: {e}")
```

### Constraints

- **File Size**: Maximum 200MB per file
- **Rate Limits**: 200 requests per 60 seconds, 200 concurrent max
- **Languages**: Maximum 4 language hints per request
- **Supported Types**: PDF, PNG, JPEG, WEBP, GIF, TIFF

### Performance Tips

1. **Use Context Manager**: Always use `async with` for proper session cleanup
2. **Language Hints**: Provide relevant language hints for better accuracy
3. **Batch Processing**: Respect rate limits when processing multiple files
4. **Error Retry**: Implement exponential backoff for rate limit errors
5. **File Validation**: Check file size and type before processing

### Integration Example

```python
from app.services.ocr_clients import DatalabOCRClient
from app.services.document_storage import document_storage_service

async def process_document(document_url: str, document_type: str):
    \"\"\"Process a document from URL and extract text.\"\"\"
    
    # Download file
    file_content = await document_storage_service.download_file(document_url)
    
    # Process with OCR
    async with DatalabOCRClient() as ocr_client:
        try:
            result = await ocr_client.process_file_content(
                file_content=file_content,
                filename=f"document.{document_type}",
                mime_type=f"application/{document_type}",
                languages=["English"]
            )
            
            return {
                "text": result['full_text'],
                "confidence": result['average_confidence'],
                "pages": result['page_count'],
                "processing_time": result['metadata']['processing_time']
            }
            
        except DatalabRateLimitError:
            # Handle rate limiting with exponential backoff
            await asyncio.sleep(60)
            return await process_document(document_url, document_type)
        
        except DatalabOCRError as e:
            # Log error and return failure
            logger.error(f"OCR processing failed: {e}")
            return {"error": str(e)}
```

### Testing

The client includes comprehensive unit tests covering:

- Initialization and configuration
- File validation
- HTTP request/response handling
- Error conditions
- Response parsing
- Session management

Run tests with:

```bash
python -m pytest tests/test_datalab_ocr.py -v
```

### API Reference

For complete Datalab API documentation, visit: https://www.datalab.to/app/docs

### Support

For issues related to:
- **Client Implementation**: Create an issue in the project repository
- **API Limits/Billing**: Contact support@datalab.to
- **OCR Accuracy**: Review language hints and file quality 