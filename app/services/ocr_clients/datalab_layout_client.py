"""
Datalab Layout API Client

Provides semantic layout detection to enhance OCR results with structural understanding.
Works alongside the existing OCR clients to identify document regions like tables, headers, etc.
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

import aiohttp
from pydantic import BaseModel

from app.config.settings import settings

logger = logging.getLogger(__name__)


class LayoutBoundingBox(BaseModel):
    """Represents a layout bounding box with semantic label."""
    
    bbox: List[float]  # [x1, y1, x2, y2] 
    polygon: List[List[float]]  # [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
    label: str  # Caption, Footnote, Formula, List-item, Page-footer, Page-header, Picture, Figure, Section-header, Table, Text, Title
    position: int  # Reading order
    confidence: float = 0.9  # Layout detection confidence


class LayoutPage(BaseModel):
    """Represents layout analysis for a single page."""
    
    page: int
    bboxes: List[LayoutBoundingBox]
    image_bbox: List[float]  # [x1, y1, x2, y2]
    
    def get_regions_by_type(self, label_type: str) -> List[LayoutBoundingBox]:
        """Get all regions of a specific type (e.g., 'Table', 'Header')."""
        return [bbox for bbox in self.bboxes if bbox.label == label_type]
    
    def get_reading_order(self) -> List[LayoutBoundingBox]:
        """Get regions sorted by reading order."""
        return sorted(self.bboxes, key=lambda x: x.position)


class LayoutAnalysisResult(BaseModel):
    """Complete layout analysis result."""
    
    success: bool
    pages: List[LayoutPage]
    page_count: int
    processing_time: float
    error: Optional[str] = None
    
    def get_all_tables(self) -> List[LayoutBoundingBox]:
        """Get all table regions across all pages."""
        tables = []
        for page in self.pages:
            tables.extend(page.get_regions_by_type("Table"))
        return tables
    
    def get_all_headers(self) -> List[LayoutBoundingBox]:
        """Get all header regions across all pages."""
        headers = []
        for page in self.pages:
            headers.extend(page.get_regions_by_type("Section-header"))
            headers.extend(page.get_regions_by_type("Title"))
        return headers


class DatalabLayoutError(Exception):
    """Base exception for Datalab Layout API errors."""
    pass


class DatalabLayoutClient:
    """
    Datalab Layout API client for semantic document structure detection.
    
    Detects and labels layout regions in documents to provide context for OCR processing.
    Integrates with existing OCR pipeline to enhance document understanding.
    """
    
    BASE_URL = "https://www.datalab.to/api/v1"
    LAYOUT_ENDPOINT = f"{BASE_URL}/layout"
    
    # Polling configuration
    DEFAULT_POLL_INTERVAL = 2  # seconds
    DEFAULT_MAX_POLLS = 300  # 10 minutes maximum
    DEFAULT_TIMEOUT = 30  # 30 seconds per request
    
    # File constraints (same as OCR)
    MAX_FILE_SIZE = 200 * 1024 * 1024  # 200MB
    SUPPORTED_MIME_TYPES = {
        "application/pdf",
        "image/png", 
        "image/jpeg",
        "image/webp",
        "image/gif",
        "image/tiff",
        "image/jpg",
    }
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Datalab Layout client.
        
        Args:
            api_key: Datalab API key. If not provided, reads from settings.
        """
        self.api_key = api_key or settings.DATALAB_API_KEY
        if not self.api_key:
            raise DatalabLayoutError("DATALAB_API_KEY is required")
        
        self.session: Optional[aiohttp.ClientSession] = None
        self.headers = {"X-Api-Key": self.api_key}
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self._ensure_session()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
    
    async def _ensure_session(self):
        """Ensure aiohttp session is created."""
        if not self.session:
            timeout = aiohttp.ClientTimeout(total=self.DEFAULT_TIMEOUT)
            self.session = aiohttp.ClientSession(
                headers=self.headers,
                timeout=timeout
            )
    
    async def close(self):
        """Close the aiohttp session."""
        if self.session:
            await self.session.close()
            self.session = None
    
    def _validate_file_size(self, size: int):
        """Validate file size is within limits."""
        if size > self.MAX_FILE_SIZE:
            raise DatalabLayoutError(f"File size {size} exceeds maximum {self.MAX_FILE_SIZE}")
    
    def _validate_mime_type(self, mime_type: str):
        """Validate MIME type is supported."""
        if mime_type not in self.SUPPORTED_MIME_TYPES:
            raise DatalabLayoutError(f"Unsupported MIME type: {mime_type}")
    
    async def _submit_layout_request(
        self,
        file_content: bytes,
        filename: str,
        mime_type: str,
        max_pages: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Submit layout analysis request to Datalab API.
        
        Args:
            file_content: File content as bytes
            filename: Original filename  
            mime_type: File MIME type
            max_pages: Optional maximum pages to process
            
        Returns:
            Initial response with request_id and check URL
        """
        await self._ensure_session()
        
        # Validate inputs
        self._validate_file_size(len(file_content))
        self._validate_mime_type(mime_type)
        
        # Prepare form data
        form_data = aiohttp.FormData()
        form_data.add_field(
            "file", file_content, filename=filename, content_type=mime_type
        )
        
        if max_pages:
            form_data.add_field("max_pages", str(max_pages))
        
        try:
            async with self.session.post(self.LAYOUT_ENDPOINT, data=form_data) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise DatalabLayoutError(f"Layout API error {response.status}: {error_text}")
                
                return await response.json()
                
        except aiohttp.ClientError as e:
            raise DatalabLayoutError(f"Layout request failed: {e}")
    
    async def _poll_for_results(
        self,
        check_url: str,
        max_polls: int = DEFAULT_MAX_POLLS,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
    ) -> Dict[str, Any]:
        """
        Poll for layout analysis results.
        
        Args:
            check_url: URL to poll for results
            max_polls: Maximum number of polling attempts
            poll_interval: Time between polls in seconds
            
        Returns:
            Final layout analysis results
        """
        await self._ensure_session()
        
        for attempt in range(max_polls):
            try:
                async with self.session.get(check_url) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise DatalabLayoutError(f"Polling error {response.status}: {error_text}")
                    
                    data = await response.json()
                    status = data.get("status")
                    
                    if status == "complete":
                        return data
                    elif status == "failed":
                        error = data.get("error", "Unknown error")
                        raise DatalabLayoutError(f"Layout analysis failed: {error}")
                    
                    # Still processing, wait and retry
                    if attempt < max_polls - 1:
                        await asyncio.sleep(poll_interval)
                        
            except aiohttp.ClientError as e:
                if attempt == max_polls - 1:
                    raise DatalabLayoutError(f"Polling failed: {e}")
                await asyncio.sleep(poll_interval)
        
        raise DatalabLayoutError(f"Layout analysis timed out after {max_polls} attempts")
    
    def _parse_layout_results(self, response_data: Dict[str, Any]) -> LayoutAnalysisResult:
        """
        Parse Datalab Layout response into structured format.
        
        Args:
            response_data: Raw response from Datalab Layout API
            
        Returns:
            Parsed layout analysis results
        """
        try:
            success = response_data.get("success", False)
            error = response_data.get("error")
            
            if not success:
                return LayoutAnalysisResult(
                    success=False,
                    pages=[],
                    page_count=0,
                    processing_time=0.0,
                    error=error or "Layout analysis failed"
                )
            
            pages = []
            for page_data in response_data.get("pages", []):
                bboxes = []
                for bbox_data in page_data.get("bboxes", []):
                    bbox = LayoutBoundingBox(
                        bbox=bbox_data.get("bbox", []),
                        polygon=bbox_data.get("polygon", []),
                        label=bbox_data.get("label", "Text"),
                        position=bbox_data.get("position", 0)
                    )
                    bboxes.append(bbox)
                
                page = LayoutPage(
                    page=page_data.get("page", 1),
                    bboxes=bboxes,
                    image_bbox=page_data.get("image_bbox", [])
                )
                pages.append(page)
            
            return LayoutAnalysisResult(
                success=True,
                pages=pages,
                page_count=response_data.get("page_count", len(pages)),
                processing_time=0.0  # Will be set by caller
            )
            
        except Exception as e:
            return LayoutAnalysisResult(
                success=False,
                pages=[],
                page_count=0,
                processing_time=0.0,
                error=f"Failed to parse layout results: {e}"
            )
    
    async def analyze_layout(
        self,
        file_content: bytes,
        filename: str,
        mime_type: str,
        max_pages: Optional[int] = None,
        max_polls: int = DEFAULT_MAX_POLLS,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
    ) -> LayoutAnalysisResult:
        """
        Analyze document layout to detect semantic regions.
        
        Args:
            file_content: File content as bytes
            filename: Original filename
            mime_type: File MIME type
            max_pages: Optional maximum pages to process
            max_polls: Maximum polling attempts
            poll_interval: Time between polls in seconds
            
        Returns:
            Layout analysis results with semantic region detection
        """
        start_time = time.time()
        
        try:
            logger.info(f"Starting layout analysis for {filename} ({len(file_content)} bytes)")
            
            # Submit layout request
            response = await self._submit_layout_request(
                file_content, filename, mime_type, max_pages
            )
            
            request_id = response.get("request_id")
            check_url = response.get("request_check_url")
            
            if not check_url:
                raise DatalabLayoutError("No check URL received from Layout API")
            
            logger.info(f"Layout analysis submitted, polling for results: {request_id}")
            
            # Poll for results
            results = await self._poll_for_results(check_url, max_polls, poll_interval)
            
            # Parse results
            processing_time = time.time() - start_time
            layout_result = self._parse_layout_results(results)
            layout_result.processing_time = processing_time
            
            logger.info(
                f"Layout analysis completed for {filename}: "
                f"{layout_result.page_count} pages, "
                f"{sum(len(page.bboxes) for page in layout_result.pages)} regions detected, "
                f"processing time: {processing_time:.2f}s"
            )
            
            return layout_result
            
        except Exception as e:
            processing_time = time.time() - start_time
            logger.error(f"Layout analysis failed for {filename} after {processing_time:.2f}s: {e}")
            
            return LayoutAnalysisResult(
                success=False,
                pages=[],
                page_count=0,
                processing_time=processing_time,
                error=str(e)
            ) 