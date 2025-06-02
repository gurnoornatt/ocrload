"""
Marker OCR Client for Datalab.to Marker API

This client provides a fallback OCR service using the Marker API,
which converts documents to structured format with text extraction.
Uses the same interface as DatalabOCRClient for seamless integration.

Based on real API testing and understanding of actual response format.
"""

import asyncio
import json
import re
from typing import Any

import aiohttp
from aiohttp import FormData

from app.config.settings import settings


class MarkerOCRError(Exception):
    """Custom exception for Marker OCR errors."""

    pass


class MarkerOCRClient:
    """
    Marker OCR client for document text extraction using Datalab.to Marker API.

    This client serves as a fallback to DatalabOCRClient when OCR confidence
    is low or when primary OCR service fails. It uses the Marker API which
    converts documents to structured format and extracts text with layout
    information.

    Features:
    - Async HTTP requests with proper session management
    - Polling mechanism for async processing
    - Response format normalization to match OCR API structure
    - Confidence estimation based on text extraction quality
    - Comprehensive error handling
    """

    def __init__(
        self,
        api_key: str | None = None,
        session: aiohttp.ClientSession | None = None,
    ):
        """
        Initialize Marker OCR client.

        Args:
            api_key: Optional API key override. Uses settings if not provided.
            session: Optional aiohttp session. Creates new if not provided.
        """
        self.api_key = (
            api_key or settings.DATALAB_API_KEY
        )  # Same key for all Datalab endpoints
        self.base_url = "https://www.datalab.to/api/v1"
        self.session = session
        self._own_session = session is None

        # Configuration
        self.max_file_size = 200 * 1024 * 1024  # 200MB limit
        self.poll_interval = 2.0  # seconds
        self.max_polls = 150  # 5 minutes max

        # Supported MIME types (same as Marker API supports)
        self.supported_mime_types = {
            "application/pdf",
            "image/png",
            "image/jpeg",
            "image/webp",
            "image/gif",
            "image/tiff",
            "image/jpg",
            "application/vnd.ms-excel",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/vnd.oasis.opendocument.spreadsheet",
            "application/msword",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/vnd.oasis.opendocument.text",
            "application/vnd.ms-powerpoint",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            "application/vnd.oasis.opendocument.presentation",
            "text/html",
            "application/epub+zip",
        }

    async def __aenter__(self):
        """Async context manager entry."""
        if self._own_session:
            self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self._own_session and self.session:
            await self.session.close()

    def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self.session is None:
            self.session = aiohttp.ClientSession()
        return self.session

    def _validate_file_content(self, file_content: bytes, mime_type: str) -> None:
        """
        Validate file content before processing.

        Args:
            file_content: Raw file bytes
            mime_type: MIME type of the file

        Raises:
            MarkerOCRError: If validation fails
        """
        if not file_content:
            raise MarkerOCRError("File content is empty")

        if len(file_content) > self.max_file_size:
            raise MarkerOCRError(
                f"File size {len(file_content)} exceeds maximum {self.max_file_size}"
            )

        if mime_type not in self.supported_mime_types:
            raise MarkerOCRError(f"Unsupported MIME type: {mime_type}")

    async def _submit_marker_request(
        self,
        file_content: bytes,
        filename: str,
        mime_type: str,
        languages: list[str] | None = None,
        max_pages: int | None = None,
        force_ocr: bool = False,
    ) -> dict[str, Any]:
        """
        Submit request to Marker API.

        Args:
            file_content: Raw file bytes
            filename: Original filename
            mime_type: MIME type
            languages: Optional language hints
            max_pages: Optional max pages to process
            force_ocr: Force OCR on every page

        Returns:
            API response with request_id and check_url

        Raises:
            MarkerOCRError: If submission fails
        """
        session = self._get_session()

        # Prepare form data
        form_data = FormData()
        form_data.add_field(
            "file", file_content, filename=filename, content_type=mime_type
        )

        # Always request JSON format for consistent parsing
        form_data.add_field("output_format", "json")

        # Language configuration (single string as per API docs)
        if languages:
            if len(languages) == 1:
                form_data.add_field("langs", languages[0])
            else:
                # Multiple languages - use comma-separated
                form_data.add_field("langs", ",".join(languages))

        # Optional parameters
        if max_pages:
            form_data.add_field("max_pages", str(max_pages))

        if force_ocr:
            form_data.add_field("force_ocr", "true")

        headers = {"X-Api-Key": self.api_key}

        try:
            async with session.post(
                f"{self.base_url}/marker", data=form_data, headers=headers
            ) as response:
                if response.status == 401:
                    raise MarkerOCRError("Authentication failed - invalid API key")
                elif response.status == 429:
                    raise MarkerOCRError("Rate limit exceeded - too many requests")
                elif response.status != 200:
                    error_text = await response.text()
                    raise MarkerOCRError(
                        f"API request failed with status {response.status}: {error_text}"
                    )

                data = await response.json()

                if not data.get("success", False):
                    error_msg = data.get("error", "Unknown error")
                    raise MarkerOCRError(f"Marker API error: {error_msg}")

                if "request_id" not in data or "request_check_url" not in data:
                    raise MarkerOCRError(
                        "Invalid API response - missing request tracking info"
                    )

                return data

        except aiohttp.ClientError as e:
            raise MarkerOCRError(f"Network error: {str(e)}")
        except json.JSONDecodeError as e:
            raise MarkerOCRError(f"Invalid JSON response: {str(e)}")

    async def _poll_for_results(self, check_url: str) -> dict[str, Any]:
        """
        Poll the API until processing is complete.

        Args:
            check_url: URL to poll for results

        Returns:
            Final processing results

        Raises:
            MarkerOCRError: If polling fails or times out
        """
        session = self._get_session()
        headers = {"X-Api-Key": self.api_key}

        for _poll_count in range(self.max_polls):
            try:
                await asyncio.sleep(self.poll_interval)

                async with session.get(check_url, headers=headers) as response:
                    if response.status != 200:
                        continue  # Retry on temporary errors

                    data = await response.json()
                    status = data.get("status", "unknown")

                    if status == "complete":
                        if not data.get("success", False):
                            error_msg = data.get("error", "Processing failed")
                            raise MarkerOCRError(f"Processing failed: {error_msg}")
                        return data

                    elif status == "failed":
                        error_msg = data.get("error", "Processing failed")
                        raise MarkerOCRError(f"Processing failed: {error_msg}")

                    # Status is 'processing' - continue polling

            except aiohttp.ClientError:
                # Network error - continue polling
                continue
            except json.JSONDecodeError:
                # Invalid JSON - continue polling
                continue

        raise MarkerOCRError(f"Polling timeout after {self.max_polls} attempts")

    def _estimate_confidence(self, json_data: dict[str, Any]) -> float:
        """
        Estimate confidence score based on text extraction quality.

        Since Marker doesn't provide confidence scores like OCR API,
        we estimate based on successful text extraction and structure.

        Args:
            json_data: Parsed JSON response from Marker API

        Returns:
            Confidence score between 0.0 and 1.0
        """
        try:
            # Base confidence for successful parsing
            confidence = 0.8

            # Check if we have structured content
            if "children" in json_data and json_data["children"]:
                confidence += 0.1

                # Count text blocks with valid content
                text_blocks = 0
                total_blocks = 0

                for child in json_data["children"]:
                    if child.get("block_type") == "Page" and "children" in child:
                        for page_child in child["children"]:
                            total_blocks += 1
                            if page_child.get("html") and page_child.get("bbox"):
                                # Extract text from HTML
                                html = page_child["html"]
                                text = re.sub(r"<[^>]+>", "", html).strip()
                                if text and len(text) > 2:  # Valid text content
                                    text_blocks += 1

                # Adjust confidence based on extraction success rate
                if total_blocks > 0:
                    success_rate = text_blocks / total_blocks
                    confidence = 0.7 + (success_rate * 0.25)  # 0.7 to 0.95 range

            return min(0.95, max(0.5, confidence))  # Clamp between 0.5 and 0.95

        except Exception:
            # Fallback confidence if analysis fails
            return 0.75

    def _convert_to_ocr_format(self, marker_response: dict[str, Any]) -> dict[str, Any]:
        """
        Convert Marker API response to OCR API compatible format.

        This normalizes the response structure to match what our application
        expects from the OCR API, enabling seamless fallback.

        Args:
            marker_response: Raw response from Marker API

        Returns:
            OCR API compatible response structure
        """
        try:
            json_data = marker_response.get("json", {})

            # Extract pages from Marker JSON structure
            pages = []
            page_count = marker_response.get("page_count", 0)

            # Process document structure
            if "children" in json_data:
                for child in json_data["children"]:
                    if child.get("block_type") == "Page":
                        page_data = self._convert_page_to_ocr_format(child)
                        if page_data:
                            pages.append(page_data)

            # If no pages extracted, create a fallback structure
            if not pages and page_count > 0:
                for i in range(page_count):
                    pages.append(
                        {
                            "page_number": i + 1,
                            "text_lines": [],
                            "languages": ["en"],
                            "image_bbox": [0.0, 0.0, 600.0, 400.0],  # Default size
                            "average_confidence": 0.5,
                        }
                    )

            # Calculate overall confidence
            overall_confidence = self._estimate_confidence(json_data)

            return {
                "pages": pages,
                "page_count": len(pages),
                "average_confidence": overall_confidence,
                "extraction_method": "marker",
                "success": True,
                "raw_response": marker_response,
            }

        except Exception as e:
            # Return error structure in OCR format
            return {
                "pages": [],
                "page_count": 0,
                "average_confidence": 0.0,
                "extraction_method": "marker",
                "success": False,
                "error": f"Response conversion failed: {str(e)}",
                "raw_response": marker_response,
            }

    def _convert_page_to_ocr_format(self, page_data: dict[str, Any]) -> dict[str, Any]:
        """
        Convert a single page from Marker format to OCR format.

        Args:
            page_data: Page data from Marker API

        Returns:
            OCR API compatible page structure
        """
        text_lines = []
        page_bbox = page_data.get("bbox", [0.0, 0.0, 600.0, 400.0])

        # Extract text blocks from page children
        if "children" in page_data and page_data["children"]:
            for child in page_data["children"]:
                text_line = self._convert_block_to_text_line(child)
                if text_line:
                    text_lines.append(text_line)

        # Calculate average confidence for this page
        if text_lines:
            avg_confidence = sum(
                line.get("confidence", 0.8) for line in text_lines
            ) / len(text_lines)
        else:
            avg_confidence = 0.5

        return {
            "page_number": 1,  # Marker doesn't always provide page numbers clearly
            "text_lines": text_lines,
            "languages": ["en"],  # Default to English
            "image_bbox": page_bbox,
            "average_confidence": avg_confidence,
        }

    def _convert_block_to_text_line(
        self, block_data: dict[str, Any]
    ) -> dict[str, Any] | None:
        """
        Convert a Marker text block to OCR text line format.

        Args:
            block_data: Text block from Marker API

        Returns:
            OCR compatible text line or None if conversion fails
        """
        try:
            # Extract text from HTML
            html = block_data.get("html", "")
            if not html:
                return None

            # Remove HTML tags to get clean text
            text = re.sub(r"<[^>]+>", "", html).strip()
            if not text:
                return None

            # Get bounding box
            bbox = block_data.get("bbox")
            polygon = block_data.get("polygon")

            if not bbox:
                return None

            # Convert polygon to expected format
            if polygon and len(polygon) >= 4:
                # Marker uses [[x,y], [x,y], ...] format
                formatted_polygon = polygon
            else:
                # Create polygon from bbox
                x1, y1, x2, y2 = bbox
                formatted_polygon = [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]

            # Estimate confidence based on block type and text quality
            confidence = 0.9  # High confidence for structured extraction
            block_type = block_data.get("block_type", "")
            if block_type in ["SectionHeader", "Title"]:
                confidence = 0.95  # Higher confidence for headers
            elif len(text) < 3:
                confidence = 0.7  # Lower confidence for very short text

            return {
                "text": text,
                "confidence": confidence,
                "bbox": bbox,
                "polygon": formatted_polygon,
                "block_type": block_type,  # Additional info from Marker
            }

        except Exception:
            return None

    async def process_file_content(
        self,
        file_content: bytes,
        filename: str,
        mime_type: str,
        languages: list[str] | None = None,
        max_pages: int | None = None,
        force_ocr: bool = False,
    ) -> dict[str, Any]:
        """
        Process file content using Marker API.

        Args:
            file_content: Raw file bytes
            filename: Original filename
            mime_type: MIME type of the file
            languages: Optional language hints for OCR
            max_pages: Optional maximum pages to process
            force_ocr: Force OCR on every page (useful for PDFs with bad text)

        Returns:
            Normalized OCR response format

        Raises:
            MarkerOCRError: If processing fails
        """
        # Validate input
        self._validate_file_content(file_content, mime_type)

        # Submit request
        submit_response = await self._submit_marker_request(
            file_content, filename, mime_type, languages, max_pages, force_ocr
        )

        # Poll for results
        check_url = submit_response["request_check_url"]
        marker_response = await self._poll_for_results(check_url)

        # Convert to OCR format
        ocr_response = self._convert_to_ocr_format(marker_response)

        return ocr_response

    async def process_file_path(
        self,
        file_path: str,
        languages: list[str] | None = None,
        max_pages: int | None = None,
        force_ocr: bool = False,
    ) -> dict[str, Any]:
        """
        Process file from disk using Marker API.

        Args:
            file_path: Path to file on disk
            languages: Optional language hints
            max_pages: Optional maximum pages to process
            force_ocr: Force OCR on every page

        Returns:
            Normalized OCR response format

        Raises:
            MarkerOCRError: If file not found or processing fails
        """
        try:
            import mimetypes
            from pathlib import Path

            path = Path(file_path)
            if not path.exists():
                raise MarkerOCRError(f"File not found: {file_path}")

            # Detect MIME type
            mime_type, _ = mimetypes.guess_type(file_path)
            if not mime_type:
                # Fallback MIME type detection
                if path.suffix.lower() in [".pdf"]:
                    mime_type = "application/pdf"
                elif path.suffix.lower() in [".png"]:
                    mime_type = "image/png"
                elif path.suffix.lower() in [".jpg", ".jpeg"]:
                    mime_type = "image/jpeg"
                else:
                    raise MarkerOCRError(f"Cannot determine MIME type for {file_path}")

            # Read file content
            with open(file_path, "rb") as f:
                file_content = f.read()

            return await self.process_file_content(
                file_content, path.name, mime_type, languages, max_pages, force_ocr
            )

        except FileNotFoundError:
            raise MarkerOCRError(f"File not found: {file_path}")
        except PermissionError:
            raise MarkerOCRError(f"Permission denied: {file_path}")
        except Exception as e:
            raise MarkerOCRError(f"File processing error: {str(e)}")


# Global client instance for convenience
marker_client = MarkerOCRClient()
