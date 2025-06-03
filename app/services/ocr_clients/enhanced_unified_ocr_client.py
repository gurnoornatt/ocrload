"""
Enhanced Unified OCR Client with Layout Analysis

Integrates the Datalab Layout API with existing OCR processing to provide
context-aware document understanding and improved field extraction.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path

from .unified_ocr_client import UnifiedOCRClient
from .datalab_layout_client import DatalabLayoutClient, LayoutAnalysisResult
from app.config.settings import settings

logger = logging.getLogger(__name__)


class EnhancedOCRResult:
    """Enhanced OCR result that includes layout analysis."""
    
    def __init__(self, ocr_result: Dict[str, Any], layout_result: Optional[LayoutAnalysisResult] = None):
        self.ocr_result = ocr_result
        self.layout_result = layout_result
        
    @property
    def full_text(self) -> str:
        """Get the full extracted text."""
        return self.ocr_result.get("full_text", "")
    
    @property
    def average_confidence(self) -> float:
        """Get the average OCR confidence."""
        return self.ocr_result.get("average_confidence", 0.0)
    
    @property
    def extraction_method(self) -> str:
        """Get the OCR extraction method used."""
        return self.ocr_result.get("extraction_method", "unknown")
    
    @property
    def pages(self) -> List[Dict[str, Any]]:
        """Get the OCR pages data."""
        return self.ocr_result.get("pages", [])
    
    @property
    def has_layout_analysis(self) -> bool:
        """Check if layout analysis is available."""
        return self.layout_result is not None and self.layout_result.success
    
    @property
    def total_regions(self) -> int:
        """Get total number of layout regions detected."""
        if not self.has_layout_analysis:
            return 0
        return sum(len(page.bboxes) for page in self.layout_result.pages)
    
    @property
    def detected_tables(self) -> int:
        """Get number of tables detected."""
        if not self.has_layout_analysis:
            return 0
        return len(self.layout_result.get_all_tables())
    
    @property
    def detected_headers(self) -> int:
        """Get number of headers detected."""
        if not self.has_layout_analysis:
            return 0
        return len(self.layout_result.get_all_headers())
    
    def get_text_by_region_type(self, region_type: str) -> List[str]:
        """
        Extract text from specific layout regions.
        
        This is a simplified implementation - in production, you'd need
        to map OCR text coordinates to layout regions.
        """
        if not self.has_layout_analysis:
            return []
        
        # For now, return indication of available regions
        region_texts = []
        for page in self.layout_result.pages:
            regions = page.get_regions_by_type(region_type)
            for region in regions:
                # This would need coordinate mapping in production
                region_texts.append(f"[{region_type} region detected at {region.bbox}]")
        
        return region_texts
    
    def get_processing_strategy(self) -> Dict[str, Any]:
        """
        Get recommended processing strategy based on layout analysis.
        """
        strategy = {
            "has_tables": self.detected_tables > 0,
            "has_headers": self.detected_headers > 0,
            "complex_layout": self.total_regions > 5,
            "recommended_approach": "standard"
        }
        
        if self.detected_tables > 0:
            strategy["recommended_approach"] = "table_focused"
            strategy["table_extraction_priority"] = True
        elif self.detected_headers > 0:
            strategy["recommended_approach"] = "section_aware"
            strategy["header_guided_extraction"] = True
        elif self.total_regions > 10:
            strategy["recommended_approach"] = "complex_layout"
            strategy["reading_order_processing"] = True
        
        return strategy
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format compatible with existing code."""
        result = self.ocr_result.copy()
        
        if self.has_layout_analysis:
            result["layout_analysis"] = {
                "success": True,
                "total_regions": self.total_regions,
                "tables": self.detected_tables,
                "headers": self.detected_headers,
                "processing_time": self.layout_result.processing_time,
                "processing_strategy": self.get_processing_strategy()
            }
        else:
            result["layout_analysis"] = {
                "success": False,
                "error": self.layout_result.error if self.layout_result else "Layout analysis not performed"
            }
        
        return result


class EnhancedUnifiedOCRClient:
    """
    Enhanced OCR client that combines traditional OCR with semantic layout analysis.
    
    Provides context-aware document processing by understanding document structure
    before extracting text, enabling better field extraction for freight documents.
    """
    
    def __init__(self, enable_layout_analysis: bool = True):
        """
        Initialize enhanced OCR client.
        
        Args:
            enable_layout_analysis: Whether to perform layout analysis alongside OCR
        """
        self.ocr_client = UnifiedOCRClient()
        self.layout_client = DatalabLayoutClient() if enable_layout_analysis else None
        self.enable_layout_analysis = enable_layout_analysis
        
    async def __aenter__(self):
        """Async context manager entry."""
        await self.ocr_client.__aenter__()
        if self.layout_client:
            await self.layout_client.__aenter__()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.ocr_client.__aexit__(exc_type, exc_val, exc_tb)
        if self.layout_client:
            await self.layout_client.__aexit__(exc_type, exc_val, exc_tb)
    
    async def process_file_content_enhanced(
        self,
        file_content: bytes,
        filename: str,
        mime_type: str,
        include_layout_analysis: Optional[bool] = None
    ) -> EnhancedOCRResult:
        """
        Process file content with both OCR and layout analysis.
        
        Args:
            file_content: File content as bytes
            filename: Original filename
            mime_type: File MIME type
            include_layout_analysis: Override default layout analysis setting
            
        Returns:
            Enhanced OCR result with layout understanding
        """
        # Determine if we should perform layout analysis
        perform_layout = include_layout_analysis if include_layout_analysis is not None else self.enable_layout_analysis
        perform_layout = perform_layout and self.layout_client is not None
        
        logger.info(f"Processing {filename} with enhanced OCR (layout: {perform_layout})")
        
        # Run OCR and layout analysis in parallel if both are enabled
        if perform_layout:
            ocr_task = self.ocr_client.process_file_content(file_content, filename, mime_type)
            layout_task = self.layout_client.analyze_layout(file_content, filename, mime_type)
            
            ocr_result, layout_result = await asyncio.gather(ocr_task, layout_task)
        else:
            ocr_result = await self.ocr_client.process_file_content(file_content, filename, mime_type)
            layout_result = None
        
        return EnhancedOCRResult(ocr_result, layout_result)
    
    async def process_file_content(
        self,
        file_content: bytes,
        filename: str,
        mime_type: str
    ) -> Dict[str, Any]:
        """
        Process file content with backward compatibility.
        
        This method maintains compatibility with existing code while adding layout analysis.
        """
        enhanced_result = await self.process_file_content_enhanced(file_content, filename, mime_type)
        return enhanced_result.to_dict()
    
    async def analyze_document_structure(
        self,
        file_content: bytes,
        filename: str,
        mime_type: str
    ) -> Dict[str, Any]:
        """
        Analyze document structure to determine optimal processing strategy.
        
        Useful for deciding how to approach field extraction before processing.
        """
        if not self.layout_client:
            return {
                "error": "Layout analysis not enabled",
                "recommended_strategy": "standard"
            }
        
        layout_result = await self.layout_client.analyze_layout(file_content, filename, mime_type)
        
        if not layout_result.success:
            return {
                "error": layout_result.error,
                "recommended_strategy": "standard"
            }
        
        # Analyze structure
        tables = layout_result.get_all_tables()
        headers = layout_result.get_all_headers()
        total_regions = sum(len(page.bboxes) for page in layout_result.pages)
        
        # Determine document classification
        document_type = "unknown"
        confidence = 0.5
        
        if len(tables) >= 2:
            document_type = "structured_form"  # Like BOL or invoice with multiple tables
            confidence = 0.8
        elif len(tables) == 1:
            document_type = "simple_form"  # Like simple receipt or single-table document
            confidence = 0.7
        elif len(headers) >= 2:
            document_type = "sectioned_document"  # Document with clear sections
            confidence = 0.6
        elif total_regions > 10:
            document_type = "complex_text"  # Complex text document
            confidence = 0.5
        else:
            document_type = "simple_text"  # Simple text document
            confidence = 0.4
        
        # Processing recommendations
        processing_strategy = {
            "structured_form": {
                "approach": "table_focused",
                "extract_tables_first": True,
                "use_table_context": True,
                "validate_numeric_fields": True
            },
            "simple_form": {
                "approach": "hybrid",
                "identify_table_regions": True,
                "use_reading_order": True,
                "standard_fallback": True
            },
            "sectioned_document": {
                "approach": "section_aware",
                "process_by_sections": True,
                "use_header_context": True,
                "maintain_section_relationships": True
            },
            "complex_text": {
                "approach": "reading_order",
                "follow_layout_sequence": True,
                "preserve_spatial_relationships": True,
                "advanced_parsing": True
            },
            "simple_text": {
                "approach": "standard",
                "basic_ocr_sufficient": True,
                "layout_benefits_minimal": True
            }
        }.get(document_type, {"approach": "standard"})
        
        return {
            "success": True,
            "document_type": document_type,
            "confidence": confidence,
            "total_regions": total_regions,
            "tables_detected": len(tables),
            "headers_detected": len(headers),
            "processing_strategy": processing_strategy,
            "recommended_ai_prompt_context": self._get_ai_prompt_context(document_type, tables, headers)
        }
    
    def _get_ai_prompt_context(self, document_type: str, tables: List, headers: List) -> str:
        """Generate AI prompt context based on layout analysis."""
        
        context_parts = []
        
        if document_type == "structured_form":
            context_parts.append("This document has a structured form layout with multiple tables.")
            context_parts.append(f"Focus on extracting data from {len(tables)} detected table regions.")
            context_parts.append("Pay special attention to numerical values, dates, and structured relationships.")
        
        elif document_type == "simple_form":
            context_parts.append("This document has a simple form layout with tabular data.")
            context_parts.append("Look for key-value pairs and structured information.")
            context_parts.append("Validate extracted numerical and date fields.")
        
        elif document_type == "sectioned_document":
            context_parts.append(f"This document is organized into {len(headers)} main sections.")
            context_parts.append("Process each section contextually and maintain relationships between sections.")
            context_parts.append("Use section headers to understand the purpose of each region.")
        
        elif document_type == "complex_text":
            context_parts.append("This document has a complex layout with multiple regions.")
            context_parts.append("Follow the natural reading order and preserve spatial relationships.")
            context_parts.append("Consider the position and context of information for accurate extraction.")
        
        else:
            context_parts.append("This document has a simple text layout.")
            context_parts.append("Standard extraction approach should be sufficient.")
        
        return " ".join(context_parts)


# Backwards compatibility alias
EnhancedOCRClient = EnhancedUnifiedOCRClient 