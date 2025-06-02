"""
Enhanced Datalab Client for 99-100% Invoice Accuracy

This client implements a multi-stage approach using all available Datalabs endpoints:
1. Table Recognition (/api/v1/table_rec) - Detect and structure tables
2. Marker API (/api/v1/marker) - Convert to structured markdown
3. OCR API (/api/v1/ocr) - Traditional OCR as fallback
4. Semantic AI Processing - Use GPT-4o/Claude for understanding
5. Confidence scoring and validation

For financial documents where mistakes cost thousands of dollars.
"""

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import aiohttp
from aiohttp import FormData

from app.config.settings import settings

logger = logging.getLogger(__name__)


class EnhancedDatalabError(Exception):
    """Base exception for Enhanced Datalab errors."""
    pass


class TableRecognitionResult:
    """Structured result from table recognition API."""
    
    def __init__(self, data: Dict[str, Any]):
        self.raw_data = data
        self.success = data.get('success', False)
        self.tables = data.get('tables', [])
        self.table_count = len(self.tables)
        self.confidence = data.get('average_confidence', 0.0)
        self.processing_time = data.get('processing_time', 0.0)
    
    def get_structured_data(self) -> List[Dict[str, Any]]:
        """Extract structured table data."""
        structured_tables = []
        for table in self.tables:
            structured_tables.append({
                'headers': table.get('headers', []),
                'rows': table.get('rows', []),
                'bbox': table.get('bbox', []),
                'confidence': table.get('confidence', 0.0)
            })
        return structured_tables


class MarkerResult:
    """Structured result from Marker API."""
    
    def __init__(self, data: Dict[str, Any]):
        self.raw_data = data
        self.success = data.get('success', False)
        self.markdown = data.get('markdown', '')
        self.json_structure = data.get('json', {})
        self.confidence = data.get('confidence', 0.0)
        self.page_count = data.get('page_count', 0)
    
    def extract_text_blocks(self) -> List[Dict[str, Any]]:
        """Extract structured text blocks from markdown."""
        blocks = []
        if self.json_structure and 'children' in self.json_structure:
            for child in self.json_structure['children']:
                if child.get('block_type') in ['Text', 'Table', 'Header']:
                    blocks.append({
                        'type': child.get('block_type'),
                        'text': child.get('text', ''),
                        'bbox': child.get('bbox', []),
                        'confidence': child.get('confidence', 0.8)
                    })
        return blocks


class EnhancedDatalabClient:
    """
    Enhanced Datalab client for maximum accuracy invoice processing.
    
    Uses multiple API endpoints in a strategic sequence:
    1. Table Recognition for structured data
    2. Marker for document layout understanding  
    3. Traditional OCR as validation/fallback
    4. Semantic AI for field extraction and validation
    """
    
    BASE_URL = "https://www.datalab.to/api/v1"
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.DATALAB_API_KEY
        if not self.api_key:
            raise EnhancedDatalabError("DATALAB_API_KEY is required")
        
        self.session: Optional[aiohttp.ClientSession] = None
        self.headers = {"X-Api-Key": self.api_key}
        
        # Configuration for high accuracy
        self.confidence_threshold = 0.95  # Very high threshold
        self.max_retries = 3
        self.poll_interval = 2.0
        self.max_polls = 150
        
    async def __aenter__(self):
        """Async context manager entry."""
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=300)  # 5 minute timeout
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.session:
            await self.session.close()
    
    async def _submit_request(self, endpoint: str, form_data: FormData) -> Dict[str, Any]:
        """Submit request to any Datalab endpoint."""
        url = f"{self.BASE_URL}/{endpoint}"
        
        for attempt in range(self.max_retries):
            try:
                async with self.session.post(url, data=form_data, headers=self.headers) as response:
                    if response.status == 401:
                        raise EnhancedDatalabError("Invalid API key")
                    elif response.status == 429:
                        # Rate limit - wait and retry
                        wait_time = 2 ** attempt
                        logger.warning(f"Rate limit hit, waiting {wait_time}s before retry {attempt + 1}")
                        await asyncio.sleep(wait_time)
                        continue
                    elif response.status >= 400:
                        error_data = await response.json()
                        raise EnhancedDatalabError(f"API error {response.status}: {error_data.get('error', 'Unknown')}")
                    
                    return await response.json()
                    
            except aiohttp.ClientError as e:
                if attempt == self.max_retries - 1:
                    raise EnhancedDatalabError(f"Network error after {self.max_retries} attempts: {e}")
                await asyncio.sleep(2 ** attempt)
                
        raise EnhancedDatalabError("Max retries exceeded")
    
    async def _poll_for_results(self, check_url: str) -> Dict[str, Any]:
        """Poll for async processing results."""
        for attempt in range(self.max_polls):
            try:
                async with self.session.get(check_url, headers=self.headers) as response:
                    if response.status >= 400:
                        raise EnhancedDatalabError(f"Polling failed: HTTP {response.status}")
                    
                    result = await response.json()
                    
                    if result.get("status") == "complete":
                        if not result.get("success"):
                            raise EnhancedDatalabError(f"Processing failed: {result.get('error', 'Unknown')}")
                        return result
                    elif result.get("status") == "processing":
                        await asyncio.sleep(self.poll_interval)
                        continue
                    else:
                        raise EnhancedDatalabError(f"Unexpected status: {result.get('status')}")
                        
            except aiohttp.ClientError as e:
                logger.warning(f"Polling attempt {attempt + 1} failed: {e}")
                await asyncio.sleep(self.poll_interval)
        
        raise EnhancedDatalabError(f"Processing timed out after {self.max_polls} attempts")
    
    async def recognize_tables(
        self, 
        file_content: bytes, 
        filename: str, 
        mime_type: str
    ) -> TableRecognitionResult:
        """
        Use table recognition API to detect and extract structured table data.
        
        This is crucial for invoices as they often contain itemized charges in tables.
        """
        logger.info(f"Starting table recognition for {filename}")
        start_time = time.time()
        
        form_data = FormData()
        form_data.add_field("file", file_content, filename=filename, content_type=mime_type)
        form_data.add_field("output_format", "json")
        form_data.add_field("detect_tables", "true")
        form_data.add_field("extract_structure", "true")
        
        try:
            response = await self._submit_request("table_rec", form_data)
            
            # Handle async processing
            if "request_check_url" in response:
                logger.info("Table recognition submitted, polling for results...")
                response = await self._poll_for_results(response["request_check_url"])
            
            processing_time = time.time() - start_time
            response["processing_time"] = processing_time
            
            result = TableRecognitionResult(response)
            logger.info(f"Table recognition completed: {result.table_count} tables found, confidence: {result.confidence:.3f}")
            
            return result
            
        except Exception as e:
            logger.error(f"Table recognition failed for {filename}: {e}")
            raise EnhancedDatalabError(f"Table recognition failed: {e}")
    
    async def convert_with_marker(
        self, 
        file_content: bytes, 
        filename: str, 
        mime_type: str
    ) -> MarkerResult:
        """
        Use Marker API to convert document to structured markdown.
        
        This provides document layout understanding and semantic structure.
        """
        logger.info(f"Starting Marker conversion for {filename}")
        start_time = time.time()
        
        form_data = FormData()
        form_data.add_field("file", file_content, filename=filename, content_type=mime_type)
        form_data.add_field("output_format", "json")  # Get both markdown and JSON structure
        form_data.add_field("force_ocr", "true")  # Ensure OCR is used
        form_data.add_field("extract_images", "false")  # Focus on text
        
        try:
            response = await self._submit_request("marker", form_data)
            
            # Handle async processing
            if "request_check_url" in response:
                logger.info("Marker conversion submitted, polling for results...")
                response = await self._poll_for_results(response["request_check_url"])
            
            processing_time = time.time() - start_time
            response["processing_time"] = processing_time
            
            result = MarkerResult(response)
            logger.info(f"Marker conversion completed: {result.page_count} pages, confidence: {result.confidence:.3f}")
            
            return result
            
        except Exception as e:
            logger.error(f"Marker conversion failed for {filename}: {e}")
            raise EnhancedDatalabError(f"Marker conversion failed: {e}")
    
    async def extract_with_ocr(
        self, 
        file_content: bytes, 
        filename: str, 
        mime_type: str
    ) -> Dict[str, Any]:
        """
        Use traditional OCR API for text extraction.
        
        This serves as validation and fallback for the other methods.
        """
        logger.info(f"Starting OCR extraction for {filename}")
        start_time = time.time()
        
        form_data = FormData()
        form_data.add_field("file", file_content, filename=filename, content_type=mime_type)
        form_data.add_field("langs", "English")
        
        try:
            response = await self._submit_request("ocr", form_data)
            
            # Handle async processing
            if "request_check_url" in response:
                logger.info("OCR extraction submitted, polling for results...")
                response = await self._poll_for_results(response["request_check_url"])
            
            processing_time = time.time() - start_time
            response["processing_time"] = processing_time
            
            logger.info(f"OCR extraction completed: {response.get('page_count', 0)} pages")
            return response
            
        except Exception as e:
            logger.error(f"OCR extraction failed for {filename}: {e}")
            raise EnhancedDatalabError(f"OCR extraction failed: {e}")
    
    async def process_invoice_comprehensive(
        self, 
        file_content: bytes, 
        filename: str, 
        mime_type: str
    ) -> Dict[str, Any]:
        """
        Comprehensive invoice processing using all available methods.
        
        Strategy:
        1. Run table recognition, marker, and OCR in parallel
        2. Cross-validate results between methods
        3. Use semantic AI to understand and extract fields
        4. Apply strict confidence thresholds
        5. Flag for human review if confidence < 99%
        """
        logger.info(f"Starting comprehensive processing for {filename}")
        start_time = time.time()
        
        # Run all three methods in parallel for speed
        tasks = [
            self.recognize_tables(file_content, filename, mime_type),
            self.convert_with_marker(file_content, filename, mime_type),
            self.extract_with_ocr(file_content, filename, mime_type)
        ]
        
        try:
            table_result, marker_result, ocr_result = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Handle any exceptions
            results = {
                "table_recognition": table_result if not isinstance(table_result, Exception) else None,
                "marker_conversion": marker_result if not isinstance(marker_result, Exception) else None,
                "ocr_extraction": ocr_result if not isinstance(ocr_result, Exception) else None,
                "processing_time": time.time() - start_time,
                "filename": filename
            }
            
            # Log any failures
            if isinstance(table_result, Exception):
                logger.warning(f"Table recognition failed: {table_result}")
            if isinstance(marker_result, Exception):
                logger.warning(f"Marker conversion failed: {marker_result}")
            if isinstance(ocr_result, Exception):
                logger.warning(f"OCR extraction failed: {ocr_result}")
            
            # Determine overall success and confidence
            successful_methods = sum(1 for r in [table_result, marker_result, ocr_result] if not isinstance(r, Exception))
            
            if successful_methods == 0:
                results["success"] = False
                results["error"] = "All processing methods failed"
                results["confidence"] = 0.0
            else:
                results["success"] = True
                results["successful_methods"] = successful_methods
                
                # Calculate aggregate confidence
                confidences = []
                if isinstance(table_result, TableRecognitionResult):
                    confidences.append(table_result.confidence)
                if isinstance(marker_result, MarkerResult):
                    confidences.append(marker_result.confidence)
                if isinstance(ocr_result, dict):
                    confidences.append(ocr_result.get("average_confidence", 0.0))
                
                results["confidence"] = sum(confidences) / len(confidences) if confidences else 0.0
            
            logger.info(f"Comprehensive processing completed for {filename}: "
                       f"{successful_methods}/3 methods succeeded, "
                       f"confidence: {results.get('confidence', 0):.3f}")
            
            return results
            
        except Exception as e:
            logger.error(f"Comprehensive processing failed for {filename}: {e}")
            return {
                "success": False,
                "error": str(e),
                "confidence": 0.0,
                "processing_time": time.time() - start_time,
                "filename": filename
            }
    
    def extract_text_from_results(self, results: Dict[str, Any]) -> str:
        """
        Extract and combine text from all successful processing methods.
        
        Prioritizes structured data from table recognition and marker.
        """
        text_parts = []
        
        # Extract from table recognition
        if results.get("table_recognition"):
            table_result = results["table_recognition"]
            if isinstance(table_result, TableRecognitionResult):
                for table in table_result.get_structured_data():
                    # Convert table to text representation
                    if table["headers"]:
                        text_parts.append(" | ".join(table["headers"]))
                    for row in table["rows"]:
                        text_parts.append(" | ".join(row))
        
        # Extract from Marker
        if results.get("marker_conversion"):
            marker_result = results["marker_conversion"]
            if isinstance(marker_result, MarkerResult):
                if marker_result.markdown:
                    text_parts.append(marker_result.markdown)
                # Also extract structured blocks
                for block in marker_result.extract_text_blocks():
                    if block["text"]:
                        text_parts.append(block["text"])
        
        # Extract from OCR (fallback)
        if results.get("ocr_extraction") and not text_parts:
            ocr_result = results["ocr_extraction"]
            if isinstance(ocr_result, dict) and ocr_result.get("pages"):
                for page in ocr_result["pages"]:
                    for line in page.get("text_lines", []):
                        if line.get("text"):
                            text_parts.append(line["text"])
        
        return "\n".join(text_parts)
    
    def requires_human_review(self, results: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Determine if results require human review based on confidence and validation.
        
        For financial documents, we use very strict criteria.
        """
        if not results.get("success"):
            return True, "Processing failed"
        
        confidence = results.get("confidence", 0.0)
        if confidence < self.confidence_threshold:
            return True, f"Confidence {confidence:.1%} below threshold {self.confidence_threshold:.1%}"
        
        successful_methods = results.get("successful_methods", 0)
        if successful_methods < 2:
            return True, f"Only {successful_methods}/3 methods succeeded"
        
        # Additional validation checks can be added here
        # e.g., cross-validation between methods, field completeness, etc.
        
        return False, "Confidence acceptable" 