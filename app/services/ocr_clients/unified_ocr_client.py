"""
Unified OCR Client with Automatic Failover

This service provides a unified interface to OCR functionality with
automatic failover from Datalab OCR to Marker API when:
1. Datalab OCR fails or is unavailable
2. Datalab OCR returns confidence < 0.5
3. Network errors or timeouts occur

Implements the same interface as individual clients for seamless integration.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Union, Any

from .datalab_client import DatalabOCRClient, DatalabOCRError
from .marker_client import MarkerOCRClient, MarkerOCRError


logger = logging.getLogger(__name__)


class UnifiedOCRError(Exception):
    """Exception raised when both OCR services fail."""
    pass


class UnifiedOCRClient:
    """
    Unified OCR client with automatic failover capabilities.
    
    This client attempts OCR using Datalab first, then falls back to Marker
    if Datalab fails or returns low confidence results. Provides a unified
    interface that abstracts the complexity of managing multiple OCR services.
    
    Failover Triggers:
    - Datalab API errors (network, authentication, rate limits)
    - Low confidence scores (< confidence_threshold)
    - Processing timeouts
    - Service unavailability
    
    Features:
    - Automatic failover with configurable thresholds
    - Response format normalization
    - Comprehensive logging and error tracking
    - Performance metrics and timing
    - Graceful degradation
    """
    
    def __init__(
        self,
        confidence_threshold: float = 0.5,
        api_key: Optional[str] = None,
        enable_fallback: bool = True,
        prefer_marker_for_pdfs: bool = False
    ):
        """
        Initialize unified OCR client.
        
        Args:
            confidence_threshold: Minimum confidence to avoid fallback (0.0-1.0)
            api_key: Optional API key override for both services
            enable_fallback: Whether to enable Marker fallback (default: True)
            prefer_marker_for_pdfs: Prefer Marker for PDF documents (default: False)
        """
        self.confidence_threshold = max(0.0, min(1.0, confidence_threshold))
        self.enable_fallback = enable_fallback
        self.prefer_marker_for_pdfs = prefer_marker_for_pdfs
        
        # Initialize clients
        self.datalab_client = DatalabOCRClient(api_key=api_key)
        self.marker_client = MarkerOCRClient(api_key=api_key) if enable_fallback else None
        
        # Tracking metrics
        self.stats = {
            'total_requests': 0,
            'datalab_success': 0,
            'marker_fallback': 0,
            'both_failed': 0,
            'confidence_triggered_fallback': 0,
            'error_triggered_fallback': 0
        }
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self.datalab_client.__aenter__()
        if self.marker_client:
            await self.marker_client.__aenter__()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.datalab_client.__aexit__(exc_type, exc_val, exc_tb)
        if self.marker_client:
            await self.marker_client.__aexit__(exc_type, exc_val, exc_tb)
    
    def _should_prefer_marker(self, filename: str, mime_type: str) -> bool:
        """
        Determine if we should prefer Marker for this file type.
        
        Args:
            filename: Original filename
            mime_type: MIME type of the file
            
        Returns:
            True if Marker should be tried first
        """
        if not self.prefer_marker_for_pdfs:
            return False
        
        # Prefer Marker for PDFs and document formats
        document_types = {
            'application/pdf',
            'application/msword',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'application/vnd.ms-powerpoint',
            'application/vnd.openxmlformats-officedocument.presentationml.presentation'
        }
        
        return mime_type in document_types
    
    def _is_confidence_acceptable(self, result: Dict[str, Any]) -> bool:
        """
        Check if OCR result has acceptable confidence.
        
        Args:
            result: OCR result dictionary
            
        Returns:
            True if confidence meets threshold
        """
        try:
            avg_confidence = result.get('average_confidence', 0.0)
            return avg_confidence >= self.confidence_threshold
        except (TypeError, ValueError):
            return False
    
    def _log_attempt(self, service: str, status: str, confidence: Optional[float] = None, error: Optional[str] = None):
        """Log OCR attempt for debugging and monitoring."""
        log_msg = f"OCR {service}: {status}"
        if confidence is not None:
            log_msg += f" (confidence: {confidence:.2f})"
        if error:
            log_msg += f" - {error}"
        
        if status == "success":
            logger.info(log_msg)
        elif status == "low_confidence":
            logger.warning(log_msg)
        else:
            logger.error(log_msg)
    
    async def _try_datalab_ocr(
        self,
        file_content: bytes,
        filename: str,
        mime_type: str,
        languages: Optional[List[str]] = None,
        max_pages: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Attempt OCR using Datalab API.
        
        Returns:
            OCR result dict or None if failed
        """
        try:
            logger.info(f"Attempting Datalab OCR for {filename}")
            
            result = await self.datalab_client.process_file_content(
                file_content=file_content,
                filename=filename,
                mime_type=mime_type,
                languages=languages,
                max_pages=max_pages
            )
            
            confidence = result.get('average_confidence', 0.0)
            self._log_attempt("Datalab", "success", confidence)
            
            # Add extraction method to result
            result['extraction_method'] = 'datalab'
            return result
            
        except DatalabOCRError as e:
            self._log_attempt("Datalab", "error", error=str(e))
            self.stats['error_triggered_fallback'] += 1
            return None
        except Exception as e:
            self._log_attempt("Datalab", "unexpected_error", error=str(e))
            self.stats['error_triggered_fallback'] += 1
            return None
    
    async def _try_marker_ocr(
        self,
        file_content: bytes,
        filename: str,
        mime_type: str,
        languages: Optional[List[str]] = None,
        max_pages: Optional[int] = None,
        force_ocr: bool = False
    ) -> Optional[Dict[str, Any]]:
        """
        Attempt OCR using Marker API.
        
        Returns:
            OCR result dict or None if failed
        """
        if not self.marker_client:
            return None
        
        try:
            logger.info(f"Attempting Marker OCR for {filename}")
            
            result = await self.marker_client.process_file_content(
                file_content=file_content,
                filename=filename,
                mime_type=mime_type,
                languages=languages,
                max_pages=max_pages,
                force_ocr=force_ocr
            )
            
            confidence = result.get('average_confidence', 0.0)
            self._log_attempt("Marker", "success", confidence)
            
            # Add extraction method to result
            result['extraction_method'] = 'marker'
            return result
            
        except MarkerOCRError as e:
            self._log_attempt("Marker", "error", error=str(e))
            return None
        except Exception as e:
            self._log_attempt("Marker", "unexpected_error", error=str(e))
            return None
    
    async def process_file_content(
        self,
        file_content: bytes,
        filename: str,
        mime_type: str,
        languages: Optional[List[str]] = None,
        max_pages: Optional[int] = None,
        force_marker_fallback: bool = False
    ) -> Dict[str, Any]:
        """
        Process file content with automatic failover.
        
        Args:
            file_content: Raw file bytes
            filename: Original filename
            mime_type: MIME type of the file
            languages: Optional language hints
            max_pages: Optional maximum pages to process
            force_marker_fallback: Skip Datalab and use Marker directly
            
        Returns:
            OCR result in normalized format
            
        Raises:
            UnifiedOCRError: If both services fail
        """
        self.stats['total_requests'] += 1
        
        # Determine processing order
        prefer_marker = self._should_prefer_marker(filename, mime_type)
        
        if force_marker_fallback:
            logger.info(f"Forced Marker fallback for {filename}")
            result = await self._try_marker_ocr(
                file_content, filename, mime_type, languages, max_pages, force_ocr=True
            )
            if result:
                self.stats['marker_fallback'] += 1
                return result
        elif prefer_marker:
            # Try Marker first for certain document types
            logger.info(f"Preferring Marker for document type: {mime_type}")
            result = await self._try_marker_ocr(
                file_content, filename, mime_type, languages, max_pages
            )
            if result and self._is_confidence_acceptable(result):
                self.stats['marker_fallback'] += 1
                return result
            # Fall through to try Datalab
        
        # Primary attempt: Datalab OCR
        datalab_result = await self._try_datalab_ocr(
            file_content, filename, mime_type, languages, max_pages
        )
        
        if datalab_result:
            # Check if confidence is acceptable
            if self._is_confidence_acceptable(datalab_result):
                self.stats['datalab_success'] += 1
                return datalab_result
            else:
                # Low confidence - check if fallback is enabled
                confidence = datalab_result.get('average_confidence', 0.0)
                if not self.enable_fallback:
                    # Return low confidence result if fallback disabled
                    logger.warning(f"Datalab OCR confidence {confidence:.2f} below threshold {self.confidence_threshold}, but fallback disabled, returning result")
                    self.stats['datalab_success'] += 1  # Still count as Datalab success since we're using it
                    return datalab_result
                else:
                    # Trigger fallback
                    logger.warning(
                        f"Datalab OCR confidence {confidence:.2f} below threshold {self.confidence_threshold}, "
                        f"attempting fallback for {filename}"
                    )
                    self.stats['confidence_triggered_fallback'] += 1
        
        # Fallback attempt: Marker OCR
        if not self.enable_fallback:
            # If we get here, datalab_result is None (failed completely)
            raise UnifiedOCRError("Datalab OCR failed and fallback is disabled")
        
        marker_result = await self._try_marker_ocr(
            file_content, filename, mime_type, languages, max_pages, force_ocr=True
        )
        
        if marker_result:
            self.stats['marker_fallback'] += 1
            logger.info(f"Successfully failed over to Marker for {filename}")
            return marker_result
        
        # Both services failed
        self.stats['both_failed'] += 1
        
        # Return the best result we got, or raise error
        if datalab_result:
            logger.warning("Both services had issues, returning Datalab result with low confidence")
            return datalab_result
        
        raise UnifiedOCRError(
            f"Both Datalab OCR and Marker failed for {filename}. "
            "Check API keys, network connectivity, and file format."
        )
    
    async def process_file_path(
        self,
        file_path: str,
        languages: Optional[List[str]] = None,
        max_pages: Optional[int] = None,
        force_marker_fallback: bool = False
    ) -> Dict[str, Any]:
        """
        Process file from disk with automatic failover.
        
        Args:
            file_path: Path to file on disk
            languages: Optional language hints
            max_pages: Optional maximum pages to process
            force_marker_fallback: Skip Datalab and use Marker directly
            
        Returns:
            OCR result in normalized format
            
        Raises:
            UnifiedOCRError: If file not found or both services fail
        """
        try:
            import mimetypes
            from pathlib import Path
            
            path = Path(file_path)
            if not path.exists():
                raise UnifiedOCRError(f"File not found: {file_path}")
            
            # Detect MIME type
            mime_type, _ = mimetypes.guess_type(file_path)
            if not mime_type:
                # Fallback MIME type detection
                suffix = path.suffix.lower()
                mime_map = {
                    '.pdf': 'application/pdf',
                    '.png': 'image/png',
                    '.jpg': 'image/jpeg',
                    '.jpeg': 'image/jpeg',
                    '.gif': 'image/gif',
                    '.tiff': 'image/tiff',
                    '.webp': 'image/webp'
                }
                mime_type = mime_map.get(suffix)
                if not mime_type:
                    raise UnifiedOCRError(f"Cannot determine MIME type for {file_path}")
            
            # Read file content
            with open(file_path, 'rb') as f:
                file_content = f.read()
            
            return await self.process_file_content(
                file_content, path.name, mime_type, languages, max_pages, force_marker_fallback
            )
            
        except FileNotFoundError:
            raise UnifiedOCRError(f"File not found: {file_path}")
        except PermissionError:
            raise UnifiedOCRError(f"Permission denied: {file_path}")
        except Exception as e:
            if isinstance(e, UnifiedOCRError):
                raise
            raise UnifiedOCRError(f"File processing error: {str(e)}")
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get performance and usage statistics.
        
        Returns:
            Dictionary with usage statistics
        """
        total = self.stats['total_requests']
        if total == 0:
            return {**self.stats, 'success_rate': 0.0, 'fallback_rate': 0.0}
        
        success_count = self.stats['datalab_success'] + self.stats['marker_fallback']
        success_rate = success_count / total
        fallback_rate = self.stats['marker_fallback'] / total
        
        return {
            **self.stats,
            'success_rate': success_rate,
            'fallback_rate': fallback_rate,
            'confidence_threshold': self.confidence_threshold
        }
    
    def reset_stats(self):
        """Reset performance statistics."""
        for key in self.stats:
            self.stats[key] = 0


# Global unified client instance for convenience
unified_ocr_client = UnifiedOCRClient() 