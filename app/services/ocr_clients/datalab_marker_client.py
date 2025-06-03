"""
Datalab Marker Client for Enhanced Document Processing

Provides structured markdown output from documents using Datalab's Marker API.
Supports force_ocr=True and use_llm=True for enhanced accuracy.

Now includes image preprocessing for optimal OCR results:
- Automatic deskewing and rotation correction
- Color and contrast enhancement
- Noise reduction and sharpening
- Resolution optimization
"""

import asyncio
import base64
import os
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import aiofiles
import aiohttp

# Import the image preprocessor
from ..image_preprocessor import ImagePreprocessor


@dataclass
class MarkerResult:
    """Result from Datalab Marker API processing."""
    
    success: bool
    markdown_content: Optional[str] = None
    images: Optional[Dict[str, str]] = None
    metadata: Optional[Dict] = None
    page_count: Optional[int] = None
    processing_time: Optional[float] = None
    error: Optional[str] = None
    request_id: Optional[str] = None
    
    @property
    def content_length(self) -> int:
        """Get length of markdown content."""
        return len(self.markdown_content) if self.markdown_content else 0
    
    def get_tables(self) -> List[str]:
        """Extract table sections from markdown content."""
        if not self.markdown_content:
            return []
        
        tables = []
        lines = self.markdown_content.split('\n')
        current_table = []
        in_table = False
        
        for line in lines:
            # Detect table rows (contain |)
            if '|' in line and line.strip():
                if not in_table:
                    in_table = True
                    current_table = [line]
                else:
                    current_table.append(line)
            else:
                if in_table and current_table:
                    # End of table
                    tables.append('\n'.join(current_table))
                    current_table = []
                    in_table = False
        
        # Don't forget the last table
        if in_table and current_table:
            tables.append('\n'.join(current_table))
        
        return tables
    
    def get_sections(self) -> List[Tuple[str, str]]:
        """Extract sections with headers from markdown content."""
        if not self.markdown_content:
            return []
        
        sections = []
        lines = self.markdown_content.split('\n')
        current_header = None
        current_content = []
        
        for line in lines:
            # Detect headers (start with #)
            if line.strip().startswith('#'):
                # Save previous section
                if current_header and current_content:
                    sections.append((current_header, '\n'.join(current_content).strip()))
                
                # Start new section
                current_header = line.strip()
                current_content = []
            else:
                if current_header:
                    current_content.append(line)
        
        # Don't forget the last section
        if current_header and current_content:
            sections.append((current_header, '\n'.join(current_content).strip()))
        
        return sections


class DatalabMarkerClient:
    """
    Async client for Datalab Marker API.
    
    Converts documents to structured markdown using:
    - force_ocr=True for clean OCR text
    - use_llm=True for enhanced table/form accuracy
    - output_format='markdown' for structured output
    """
    
    def __init__(self, preprocessing_enabled: bool = True, preprocessing_config: Optional[Dict] = None):
        """
        Initialize Datalab Marker client with image preprocessing.
        
        Args:
            preprocessing_enabled: Whether to enable image preprocessing
            preprocessing_config: Optional preprocessing configuration
        """
        self.api_key = os.getenv("DATALAB_API_KEY")
        self.base_url = "https://www.datalab.to/api/v1"
        
        # Initialize image preprocessor
        if preprocessing_config is None:
            preprocessing_config = {'enabled': preprocessing_enabled}
        else:
            preprocessing_config['enabled'] = preprocessing_enabled
        
        self.preprocessor = ImagePreprocessor(preprocessing_config)
        
        if not self.api_key:
            raise ValueError("DATALAB_API_KEY environment variable is required")
        
        # Session will be created in __aenter__
        self.session = None
    
    async def __aenter__(self):
        """Async context manager entry."""
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=600),  # 10 minutes total
            headers={"X-Api-Key": self.api_key}
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.session:
            await self.session.close()
    
    async def process_document(
        self,
        file_content: bytes,
        filename: str,
        mime_type: str,
        language: str = "English",
        force_ocr: bool = True,
        use_llm: bool = True,
        output_format: str = "markdown",
        paginate: bool = False,
        strip_existing_ocr: bool = False,
        disable_image_extraction: bool = False,
        max_pages: Optional[int] = None,
        max_polls: int = 300,
        poll_interval: float = 2.0
    ) -> MarkerResult:
        """
        Process document using Datalab Marker API.
        
        Args:
            file_content: Document bytes
            filename: Original filename
            mime_type: MIME type of the document
            language: Language for OCR (default: English)
            force_ocr: Force OCR on every page (default: True)
            use_llm: Use LLM for enhanced accuracy (default: True)
            output_format: Output format (default: markdown)
            paginate: Add page delimiters (default: False)
            strip_existing_ocr: Remove existing OCR text (default: False)
            disable_image_extraction: Disable image extraction (default: False)
            max_pages: Maximum pages to process (optional)
            max_polls: Maximum polling attempts (default: 300)
            poll_interval: Seconds between polls (default: 2.0)
        
        Returns:
            MarkerResult with processing results
        """
        start_time = time.time()
        
        try:
            # Step 1: Submit processing request
            request_id = await self._submit_request(
                file_content=file_content,
                filename=filename,
                mime_type=mime_type,
                language=language,
                force_ocr=force_ocr,
                use_llm=use_llm,
                output_format=output_format,
                paginate=paginate,
                strip_existing_ocr=strip_existing_ocr,
                disable_image_extraction=disable_image_extraction,
                max_pages=max_pages
            )
            
            if not request_id:
                return MarkerResult(
                    success=False,
                    error="Failed to submit processing request",
                    processing_time=time.time() - start_time
                )
            
            # Step 2: Poll for results
            result = await self._poll_for_results(
                request_id=request_id,
                max_polls=max_polls,
                poll_interval=poll_interval
            )
            
            result.processing_time = time.time() - start_time
            return result
            
        except Exception as e:
            return MarkerResult(
                success=False,
                error=f"Processing failed: {str(e)}",
                processing_time=time.time() - start_time
            )
    
    async def _submit_request(
        self,
        file_content: bytes,
        filename: str,
        mime_type: str,
        language: str,
        force_ocr: bool,
        use_llm: bool,
        output_format: str,
        paginate: bool,
        strip_existing_ocr: bool,
        disable_image_extraction: bool,
        max_pages: Optional[int]
    ) -> Optional[str]:
        """Submit document processing request to Marker API."""
        
        if not self.session:
            raise RuntimeError("Client session not initialized. Use async context manager.")
        
        # Step 1: Preprocess image if it's an image format
        processed_content = file_content
        preprocessing_metadata = {}
        
        if mime_type.startswith('image/') and self.preprocessor.config['enabled']:
            try:
                processed_content, preprocessing_metadata = self.preprocessor.preprocess_image(
                    image_bytes=file_content,
                    filename=filename,
                    mime_type=mime_type
                )
                
                # Log preprocessing results
                if 'processing_steps' in preprocessing_metadata:
                    steps = preprocessing_metadata['processing_steps']
                    print(f"📸 Image preprocessing applied: {len(steps)} steps")
                    for step in steps:
                        print(f"   • {step}")
                
            except Exception as e:
                print(f"⚠️  Image preprocessing failed, using original: {e}")
                processed_content = file_content
                preprocessing_metadata = {'preprocessing': 'failed', 'error': str(e)}
        
        # Step 2: Prepare multipart form data
        data = aiohttp.FormData()
        
        # Add processed file
        data.add_field('file', processed_content, filename=filename, content_type=mime_type)
        
        # Add parameters
        data.add_field('langs', language)
        data.add_field('force_ocr', str(force_ocr).lower())
        data.add_field('use_llm', str(use_llm).lower())
        data.add_field('output_format', output_format)
        data.add_field('paginate', str(paginate).lower())
        data.add_field('strip_existing_ocr', str(strip_existing_ocr).lower())
        data.add_field('disable_image_extraction', str(disable_image_extraction).lower())
        
        if max_pages is not None:
            data.add_field('max_pages', str(max_pages))
        
        # Step 3: Submit request
        url = f"{self.base_url}/marker"
        
        async with self.session.post(url, data=data) as response:
            if response.status != 200:
                error_text = await response.text()
                raise Exception(f"API request failed: {response.status} - {error_text}")
            
            result = await response.json()
            
            if not result.get('success'):
                raise Exception(f"API request failed: {result.get('error', 'Unknown error')}")
            
            # Store preprocessing metadata for later use
            request_id = result.get('request_id')
            if hasattr(self, '_preprocessing_metadata'):
                self._preprocessing_metadata[request_id] = preprocessing_metadata
            else:
                self._preprocessing_metadata = {request_id: preprocessing_metadata}
            
            return request_id
    
    async def _poll_for_results(
        self,
        request_id: str,
        max_polls: int,
        poll_interval: float
    ) -> MarkerResult:
        """Poll for processing results."""
        
        if not self.session:
            raise RuntimeError("Client session not initialized. Use async context manager.")
        
        check_url = f"{self.base_url}/marker/{request_id}"
        
        for i in range(max_polls):
            await asyncio.sleep(poll_interval)
            
            async with self.session.get(check_url) as response:
                if response.status != 200:
                    error_text = await response.text()
                    return MarkerResult(
                        success=False,
                        error=f"Polling failed: {response.status} - {error_text}",
                        request_id=request_id
                    )
                
                data = await response.json()
                
                # Check if processing is complete
                if data.get('status') == 'complete':
                    if data.get('success', False):
                        # Get preprocessing metadata if available
                        preprocessing_meta = getattr(self, '_preprocessing_metadata', {}).get(request_id, {})
                        
                        # Merge preprocessing metadata with API metadata
                        combined_metadata = data.get('metadata', {})
                        if preprocessing_meta:
                            combined_metadata['image_preprocessing'] = preprocessing_meta
                        
                        return MarkerResult(
                            success=True,
                            markdown_content=data.get('markdown', ''),
                            images=data.get('images', {}),
                            metadata=combined_metadata,
                            page_count=data.get('page_count'),
                            request_id=request_id
                        )
                    else:
                        return MarkerResult(
                            success=False,
                            error=data.get('error', 'Processing failed'),
                            request_id=request_id
                        )
                
                # Still processing, continue polling
                elif data.get('status') == 'processing':
                    continue
                
                # Unknown status
                else:
                    return MarkerResult(
                        success=False,
                        error=f"Unknown status: {data.get('status')}",
                        request_id=request_id
                    )
        
        # Polling timeout
        return MarkerResult(
            success=False,
            error=f"Polling timeout after {max_polls} attempts",
            request_id=request_id
        )


# Convenience function for quick processing
async def process_document_with_marker(
    file_content: bytes,
    filename: str,
    mime_type: str = "image/jpeg"
) -> MarkerResult:
    """
    Quick function to process a document with optimal Marker API settings.
    
    Uses the recommended settings for freight document processing:
    - force_ocr=True
    - use_llm=True (crucial for better structure)
    - output_format='markdown'
    - langs='English'
    """
    async with DatalabMarkerClient() as client:
        return await client.process_document(
            file_content=file_content,
            filename=filename,
            mime_type=mime_type,
            language="English",
            force_ocr=True,
            use_llm=True,  # This is very important for better structure!
            output_format="markdown"
        ) 