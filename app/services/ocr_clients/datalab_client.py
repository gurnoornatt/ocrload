"""Datalab.to OCR client implementation."""

import asyncio
import logging
import time
from typing import Dict, Any, List, Optional, Tuple, Union
from pathlib import Path
import aiohttp
import aiofiles
from aiofiles import open as aio_open

from app.config.settings import settings

logger = logging.getLogger(__name__)


class DatalabOCRError(Exception):
    """Base exception for Datalab OCR errors."""
    pass


class DatalabAuthenticationError(DatalabOCRError):
    """Authentication error with Datalab API."""
    pass


class DatalabRateLimitError(DatalabOCRError):
    """Rate limit exceeded error."""
    pass


class DatalabProcessingError(DatalabOCRError):
    """OCR processing error."""
    pass


class DatalabTimeoutError(DatalabOCRError):
    """Request timeout error."""
    pass


class DatalabOCRClient:
    """
    Datalab.to OCR API client.
    
    Handles async OCR processing with polling, retry logic, and comprehensive error handling.
    Supports images (JPG, PNG, WEBP, GIF, TIFF) and PDF files up to 200MB.
    """
    
    BASE_URL = "https://www.datalab.to/api/v1"
    OCR_ENDPOINT = f"{BASE_URL}/ocr"
    
    # Rate limiting (200 requests per 60 seconds)
    MAX_REQUESTS_PER_MINUTE = 200
    MAX_CONCURRENT_REQUESTS = 200
    
    # File constraints
    MAX_FILE_SIZE = 200 * 1024 * 1024  # 200MB
    SUPPORTED_MIME_TYPES = {
        'application/pdf',
        'image/png',
        'image/jpeg',
        'image/webp', 
        'image/gif',
        'image/tiff',
        'image/jpg'
    }
    
    # Polling configuration
    DEFAULT_POLL_INTERVAL = 2  # seconds
    DEFAULT_MAX_POLLS = 300    # 10 minutes maximum
    DEFAULT_TIMEOUT = 30       # 30 seconds per request
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Datalab OCR client.
        
        Args:
            api_key: Datalab API key. If not provided, reads from settings.
        """
        self.api_key = api_key or settings.DATALAB_API_KEY
        if not self.api_key:
            raise DatalabAuthenticationError("DATALAB_API_KEY is required")
        
        self.session: Optional[aiohttp.ClientSession] = None
        self._request_semaphore = asyncio.Semaphore(self.MAX_CONCURRENT_REQUESTS)
        
    async def __aenter__(self):
        """Async context manager entry."""
        await self._ensure_session()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
        
    async def _ensure_session(self):
        """Ensure HTTP session is created."""
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=self.DEFAULT_TIMEOUT)
            self.session = aiohttp.ClientSession(
                timeout=timeout,
                headers={
                    'X-Api-Key': self.api_key,
                    'User-Agent': 'OCR-Load-Service/1.0'
                }
            )
    
    async def close(self):
        """Close HTTP session."""
        if self.session and not self.session.closed:
            await self.session.close()
            self.session = None
    
    def _validate_file_size(self, file_size: int) -> None:
        """Validate file size constraints."""
        if file_size <= 0:
            raise DatalabOCRError("File size must be greater than 0")
        if file_size > self.MAX_FILE_SIZE:
            raise DatalabOCRError(
                f"File size {file_size} bytes exceeds maximum of {self.MAX_FILE_SIZE} bytes"
            )
    
    def _validate_mime_type(self, mime_type: str) -> None:
        """Validate MIME type is supported."""
        if mime_type.lower() not in self.SUPPORTED_MIME_TYPES:
            raise DatalabOCRError(
                f"Unsupported MIME type: {mime_type}. "
                f"Supported types: {', '.join(self.SUPPORTED_MIME_TYPES)}"
            )
    
    async def _submit_ocr_request(
        self,
        file_content: bytes,
        filename: str,
        mime_type: str,
        languages: Optional[List[str]] = None,
        max_pages: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Submit OCR request to Datalab API.
        
        Args:
            file_content: File content as bytes
            filename: Original filename
            mime_type: File MIME type
            languages: Optional language hints (up to 4)
            max_pages: Optional maximum pages to process
            
        Returns:
            Initial response with request_id and check URL
            
        Raises:
            DatalabOCRError: On validation or request errors
        """
        await self._ensure_session()
        
        # Validate inputs
        self._validate_file_size(len(file_content))
        self._validate_mime_type(mime_type)
        
        if languages and len(languages) > 4:
            raise DatalabOCRError("Maximum 4 languages allowed")
        
        # Prepare form data
        form_data = aiohttp.FormData()
        form_data.add_field('file', file_content, filename=filename, content_type=mime_type)
        
        if languages:
            # According to API docs, langs should be a single string
            # Multiple languages can be specified but documentation unclear on format
            # Using first language for now, or comma-separated as fallback
            if len(languages) == 1:
                form_data.add_field('langs', languages[0])
            else:
                # For multiple languages, try comma-separated format
                form_data.add_field('langs', ','.join(languages))
        
        if max_pages:
            form_data.add_field('max_pages', str(max_pages))
        
        async with self._request_semaphore:
            try:
                async with self.session.post(self.OCR_ENDPOINT, data=form_data) as response:
                    response_data = await response.json()
                    
                    if response.status == 401:
                        raise DatalabAuthenticationError("Invalid API key")
                    elif response.status == 429:
                        raise DatalabRateLimitError("Rate limit exceeded")
                    elif response.status >= 400:
                        error_msg = response_data.get('error', f'HTTP {response.status}')
                        raise DatalabOCRError(f"Request failed: {error_msg}")
                    
                    if not response_data.get('success'):
                        error_msg = response_data.get('error', 'Unknown error')
                        raise DatalabProcessingError(f"OCR submission failed: {error_msg}")
                    
                    return response_data
                    
            except aiohttp.ClientError as e:
                raise DatalabOCRError(f"Network error: {e}")
            except asyncio.TimeoutError:
                raise DatalabTimeoutError("Request timed out")
    
    async def _poll_for_results(
        self,
        check_url: str,
        max_polls: int = DEFAULT_MAX_POLLS,
        poll_interval: float = DEFAULT_POLL_INTERVAL
    ) -> Dict[str, Any]:
        """
        Poll for OCR results with exponential backoff.
        
        Args:
            check_url: URL to poll for results
            max_polls: Maximum number of polling attempts
            poll_interval: Initial polling interval in seconds
            
        Returns:
            Final OCR results
            
        Raises:
            DatalabTimeoutError: If polling times out
            DatalabProcessingError: If OCR processing fails
        """
        await self._ensure_session()
        
        current_interval = poll_interval
        
        for attempt in range(max_polls):
            try:
                async with self.session.get(check_url) as response:
                    if response.status == 401:
                        raise DatalabAuthenticationError("Invalid API key")
                    elif response.status == 429:
                        raise DatalabRateLimitError("Rate limit exceeded")
                    elif response.status >= 400:
                        raise DatalabOCRError(f"Polling failed: HTTP {response.status}")
                    
                    result = await response.json()
                    
                    if result.get('status') == 'complete':
                        if not result.get('success'):
                            error_msg = result.get('error', 'Unknown processing error')
                            raise DatalabProcessingError(f"OCR processing failed: {error_msg}")
                        return result
                    elif result.get('status') == 'processing':
                        # Continue polling
                        await asyncio.sleep(current_interval)
                        # Exponential backoff with jitter
                        current_interval = min(current_interval * 1.5, 10)
                        continue
                    else:
                        # Unexpected status
                        error_msg = result.get('error', f"Unexpected status: {result.get('status')}")
                        raise DatalabProcessingError(error_msg)
                        
            except aiohttp.ClientError as e:
                logger.warning(f"Polling attempt {attempt + 1} failed: {e}")
                if attempt == max_polls - 1:
                    raise DatalabOCRError(f"Polling failed after {max_polls} attempts: {e}")
                await asyncio.sleep(current_interval)
                current_interval = min(current_interval * 1.5, 10)
        
        raise DatalabTimeoutError(f"OCR processing timed out after {max_polls} polling attempts")
    
    def _parse_ocr_results(self, response_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse Datalab OCR response into standardized format.
        
        Args:
            response_data: Raw response from Datalab API
            
        Returns:
            Parsed OCR results with text, confidence, and metadata
        """
        pages = response_data.get('pages', [])
        page_count = response_data.get('page_count', 0)
        
        parsed_results = {
            'success': True,
            'page_count': page_count,
            'pages': [],
            'full_text': '',
            'average_confidence': 0.0,
            'metadata': {
                'provider': 'datalab',
                'processing_time': None,
                'total_text_lines': 0
            }
        }
        
        total_confidence = 0.0
        total_lines = 0
        all_text_parts = []
        
        for page_data in pages:
            text_lines = page_data.get('text_lines', [])
            page_text_parts = []
            page_confidence_sum = 0.0
            
            parsed_lines = []
            for line in text_lines:
                text = line.get('text', '').strip()
                confidence = line.get('confidence', 0.0)
                
                if text:  # Only include non-empty text
                    parsed_lines.append({
                        'text': text,
                        'confidence': confidence,
                        'bbox': line.get('bbox', []),
                        'polygon': line.get('polygon', [])
                    })
                    page_text_parts.append(text)
                    page_confidence_sum += confidence
                    total_confidence += confidence
                    total_lines += 1
            
            page_text = '\n'.join(page_text_parts)
            page_avg_confidence = (
                page_confidence_sum / len(parsed_lines) if parsed_lines else 0.0
            )
            
            parsed_results['pages'].append({
                'page_number': page_data.get('page', 1),
                'text': page_text,
                'average_confidence': page_avg_confidence,
                'text_lines': parsed_lines,
                'languages': page_data.get('languages', []),
                'image_bbox': page_data.get('image_bbox', [])
            })
            
            if page_text:
                all_text_parts.append(page_text)
        
        # Combine all text
        parsed_results['full_text'] = '\n\n'.join(all_text_parts)
        
        # Calculate overall average confidence
        parsed_results['average_confidence'] = (
            total_confidence / total_lines if total_lines > 0 else 0.0
        )
        
        parsed_results['metadata']['total_text_lines'] = total_lines
        
        return parsed_results
    
    async def process_file_content(
        self,
        file_content: bytes,
        filename: str,
        mime_type: str,
        languages: Optional[List[str]] = None,
        max_pages: Optional[int] = None,
        max_polls: int = DEFAULT_MAX_POLLS,
        poll_interval: float = DEFAULT_POLL_INTERVAL
    ) -> Dict[str, Any]:
        """
        Process file content for OCR.
        
        Args:
            file_content: File content as bytes
            filename: Original filename
            mime_type: File MIME type
            languages: Optional language hints (e.g., ['English', 'Spanish'])
            max_pages: Optional maximum pages to process
            max_polls: Maximum polling attempts
            poll_interval: Initial polling interval in seconds
            
        Returns:
            Parsed OCR results
            
        Raises:
            DatalabOCRError: On processing errors
        """
        start_time = time.time()
        
        try:
            # Submit OCR request
            logger.info(f"Submitting OCR request for {filename} ({len(file_content)} bytes)")
            response = await self._submit_ocr_request(
                file_content, filename, mime_type, languages, max_pages
            )
            
            request_id = response.get('request_id')
            check_url = response.get('request_check_url')
            
            if not check_url:
                raise DatalabProcessingError("No check URL received from API")
            
            logger.info(f"OCR request submitted, polling for results: {request_id}")
            
            # Poll for results
            results = await self._poll_for_results(check_url, max_polls, poll_interval)
            
            # Parse and return results
            processing_time = time.time() - start_time
            parsed_results = self._parse_ocr_results(results)
            parsed_results['metadata']['processing_time'] = processing_time
            
            logger.info(
                f"OCR completed for {filename}: "
                f"{parsed_results['page_count']} pages, "
                f"{parsed_results['metadata']['total_text_lines']} lines, "
                f"avg confidence: {parsed_results['average_confidence']:.3f}, "
                f"processing time: {processing_time:.2f}s"
            )
            
            return parsed_results
            
        except Exception as e:
            processing_time = time.time() - start_time
            logger.error(f"OCR failed for {filename} after {processing_time:.2f}s: {e}")
            raise
    
    async def process_file_path(
        self,
        file_path: Union[str, Path],
        languages: Optional[List[str]] = None,
        max_pages: Optional[int] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Process file from local path.
        
        Args:
            file_path: Path to file
            languages: Optional language hints
            max_pages: Optional maximum pages to process
            **kwargs: Additional arguments for process_file_content
            
        Returns:
            Parsed OCR results
        """
        file_path = Path(file_path)
        
        if not file_path.exists():
            raise DatalabOCRError(f"File not found: {file_path}")
        
        # Read file content
        async with aio_open(file_path, 'rb') as f:
            file_content = await f.read()
        
        # Determine MIME type
        import mimetypes
        mime_type, _ = mimetypes.guess_type(str(file_path))
        if not mime_type:
            # Fallback based on extension
            suffix = file_path.suffix.lower()
            mime_type_map = {
                '.pdf': 'application/pdf',
                '.png': 'image/png',
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg',
                '.webp': 'image/webp',
                '.gif': 'image/gif',
                '.tiff': 'image/tiff',
                '.tif': 'image/tiff'
            }
            mime_type = mime_type_map.get(suffix, 'application/octet-stream')
        
        return await self.process_file_content(
            file_content, file_path.name, mime_type, languages, max_pages, **kwargs
        )


# Global client instance
datalab_ocr_client = DatalabOCRClient() 