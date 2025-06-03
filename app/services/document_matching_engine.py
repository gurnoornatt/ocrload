"""
Document Matching Engine Service

Groups and matches related freight documents (BOL, Invoice, Lumper) to the same load
using extracted identifiers, address validation, and temporal proximity analysis.

Features:
- Multi-document type matching (BOL, Invoice, Lumper, Accessorial)
- Fuzzy matching for identifiers and addresses
- Confidence scoring with configurable thresholds
- Mismatch flagging with detailed reasoning
- Extensible architecture for new document types
"""

import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Set, Tuple
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from app.models.database import (
    AccessorialCharge,
    BillOfLading, 
    Invoice,
    LumperReceipt,
    Document,
    DocumentType
)
from app.services.supabase_client import supabase_service

logger = logging.getLogger(__name__)


class DocumentIdentifiers(BaseModel):
    """Normalized identifiers extracted from a document."""
    
    document_id: UUID
    document_type: DocumentType
    
    # Core identifiers
    bol_numbers: Set[str] = Field(default_factory=set)
    pro_numbers: Set[str] = Field(default_factory=set)
    invoice_numbers: Set[str] = Field(default_factory=set)
    customer_order_numbers: Set[str] = Field(default_factory=set)
    
    # Address information
    shipper_name: Optional[str] = None
    shipper_address: Optional[str] = None
    consignee_name: Optional[str] = None
    consignee_address: Optional[str] = None
    
    # Temporal information
    document_date: Optional[datetime] = None
    pickup_date: Optional[datetime] = None
    delivery_date: Optional[datetime] = None
    
    # Financial information
    total_amount: Optional[float] = None
    
    # Metadata
    confidence: float = 0.0
    extraction_timestamp: datetime = Field(default_factory=datetime.now)


class DocumentGroup(BaseModel):
    """A group of related documents for the same load."""
    
    group_id: UUID = Field(default_factory=uuid4)
    documents: List[DocumentIdentifiers] = Field(default_factory=list)
    
    # Matching metrics
    confidence_score: float = 0.0
    match_reasons: List[str] = Field(default_factory=list)
    mismatch_flags: List[str] = Field(default_factory=list)
    
    # Group characteristics
    dominant_identifiers: Dict[str, str] = Field(default_factory=dict)
    date_range: Optional[Tuple[datetime, datetime]] = None
    total_documents: int = 0
    
    # Status
    needs_review: bool = False
    completeness_score: float = 0.0
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class MatchingConfiguration(BaseModel):
    """Configuration parameters for document matching."""
    
    # Identifier matching thresholds
    exact_match_weight: float = 1.0
    fuzzy_match_weight: float = 0.7
    fuzzy_threshold: float = 0.8
    
    # Address matching parameters
    address_similarity_threshold: float = 0.75
    name_similarity_threshold: float = 0.80
    
    # Temporal matching parameters
    max_date_difference_days: int = 14
    strict_date_window_days: int = 7
    
    # Confidence thresholds
    high_confidence_threshold: float = 0.85
    medium_confidence_threshold: float = 0.65
    review_threshold: float = 0.40
    
    # Group completeness requirements
    required_document_types: Set[DocumentType] = Field(
        default_factory=lambda: {DocumentType.INVOICE}
    )
    preferred_document_types: Set[DocumentType] = Field(
        default_factory=lambda: {DocumentType.INVOICE, DocumentType.POD}
    )


class DocumentMatchingEngine:
    """Core engine for matching freight documents to loads."""
    
    def __init__(self, config: Optional[MatchingConfiguration] = None):
        """Initialize the matching engine with configuration."""
        self.config = config or MatchingConfiguration()
        self.supabase = supabase_service
        logger.info("Document Matching Engine initialized")
    
    async def extract_document_identifiers(
        self, 
        document: Document
    ) -> DocumentIdentifiers:
        """
        Extract normalized identifiers from a document.
        
        Args:
            document: Document object with parsed_data
            
        Returns:
            DocumentIdentifiers with normalized fields
        """
        identifiers = DocumentIdentifiers(
            document_id=document.id,
            document_type=document.type,
            confidence=document.confidence or 0.0
        )
        
        if not document.parsed_data:
            logger.warning(f"No parsed data for document {document.id}")
            return identifiers
        
        # Extract identifiers based on document type
        if document.type == DocumentType.INVOICE:
            await self._extract_invoice_identifiers(document.parsed_data, identifiers)
        elif document.type == DocumentType.POD:  # BOL documents stored as POD type
            await self._extract_bol_identifiers(document.parsed_data, identifiers)
        elif document.type == DocumentType.LUMPER:
            await self._extract_lumper_identifiers(document.parsed_data, identifiers)
        else:
            logger.info(f"Unsupported document type for matching: {document.type}")
        
        return identifiers
    
    async def _extract_invoice_identifiers(
        self, 
        parsed_data: Dict[str, Any], 
        identifiers: DocumentIdentifiers
    ) -> None:
        """Extract identifiers from invoice parsed data."""
        
        # Core identifiers
        if invoice_num := parsed_data.get("invoice_number"):
            identifiers.invoice_numbers.add(self._normalize_identifier(invoice_num))
        
        # Look for BOL/PRO references in line items
        line_items = parsed_data.get("line_items", [])
        for item in line_items:
            if isinstance(item, dict):
                # Check for BOL references
                item_desc = str(item.get("description", "")).upper()
                bol_matches = re.findall(r"BOL[#:\s]*([A-Z0-9\-_]+)", item_desc)
                pro_matches = re.findall(r"PRO[#:\s]*([A-Z0-9\-_]+)", item_desc)
                
                for bol in bol_matches:
                    identifiers.bol_numbers.add(self._normalize_identifier(bol))
                for pro in pro_matches:
                    identifiers.pro_numbers.add(self._normalize_identifier(pro))
        
        # Address information
        identifiers.shipper_name = self._normalize_name(parsed_data.get("vendor_name"))
        identifiers.consignee_name = self._normalize_name(parsed_data.get("customer_name"))
        identifiers.shipper_address = self._normalize_address(parsed_data.get("vendor_address"))
        identifiers.consignee_address = self._normalize_address(parsed_data.get("customer_address"))
        
        # Temporal information
        identifiers.document_date = self._parse_date(parsed_data.get("invoice_date"))
        identifiers.total_amount = parsed_data.get("total_amount")
    
    async def _extract_bol_identifiers(
        self, 
        parsed_data: Dict[str, Any], 
        identifiers: DocumentIdentifiers
    ) -> None:
        """Extract identifiers from BOL parsed data."""
        
        # Core identifiers
        if bol_num := parsed_data.get("bol_number"):
            identifiers.bol_numbers.add(self._normalize_identifier(bol_num))
        if pro_num := parsed_data.get("pro_number"):
            identifiers.pro_numbers.add(self._normalize_identifier(pro_num))
        
        # Address information
        identifiers.shipper_name = self._normalize_name(parsed_data.get("shipper_name"))
        identifiers.consignee_name = self._normalize_name(parsed_data.get("consignee_name"))
        identifiers.shipper_address = self._normalize_address(parsed_data.get("shipper_address"))
        identifiers.consignee_address = self._normalize_address(parsed_data.get("consignee_address"))
        
        # Temporal information
        identifiers.pickup_date = self._parse_date(parsed_data.get("pickup_date"))
        identifiers.delivery_date = self._parse_date(parsed_data.get("delivery_date"))
        identifiers.total_amount = parsed_data.get("freight_charges")
    
    async def _extract_lumper_identifiers(
        self, 
        parsed_data: Dict[str, Any], 
        identifiers: DocumentIdentifiers
    ) -> None:
        """Extract identifiers from lumper receipt parsed data."""
        
        # Core identifiers
        if bol_num := parsed_data.get("bol_number"):
            identifiers.bol_numbers.add(self._normalize_identifier(bol_num))
        
        # Address/facility information
        identifiers.consignee_name = self._normalize_name(parsed_data.get("facility_name"))
        identifiers.consignee_address = self._normalize_address(parsed_data.get("facility_address"))
        
        # Temporal information
        identifiers.document_date = self._parse_date(parsed_data.get("receipt_date"))
        identifiers.total_amount = parsed_data.get("total_amount")
    
    def _normalize_identifier(self, identifier: str) -> str:
        """Normalize identifier for consistent matching."""
        if not identifier:
            return ""
        # Remove spaces, hyphens, convert to uppercase
        return re.sub(r"[^A-Z0-9]", "", str(identifier).upper())
    
    def _normalize_name(self, name: str) -> Optional[str]:
        """Normalize company/person names for matching."""
        if not name:
            return None
        # Remove common business suffixes and normalize
        normalized = re.sub(r"\b(LLC|INC|CORP|LTD|CO\.?)\b", "", str(name).upper())
        return re.sub(r"\s+", " ", normalized).strip()
    
    def _normalize_address(self, address: str) -> Optional[str]:
        """Normalize addresses for matching."""
        if not address:
            return None
        # Basic address normalization
        normalized = str(address).upper()
        # Remove common abbreviations inconsistencies
        replacements = {
            r"\bSTREET\b": "ST",
            r"\bAVENUE\b": "AVE", 
            r"\bBOULEVARD\b": "BLVD",
            r"\bDRIVE\b": "DR",
            r"\bROAD\b": "RD",
            r"\bSUITE\b": "STE",
        }
        for pattern, replacement in replacements.items():
            normalized = re.sub(pattern, replacement, normalized)
        
        return re.sub(r"\s+", " ", normalized).strip()
    
    def _parse_date(self, date_value: Any) -> Optional[datetime]:
        """Parse various date formats to datetime."""
        if not date_value:
            return None
        
        if isinstance(date_value, datetime):
            return date_value
        
        if isinstance(date_value, str):
            # Try common formats
            formats = [
                "%Y-%m-%d",
                "%Y-%m-%d %H:%M:%S",
                "%m/%d/%Y",
                "%m-%d-%Y",
                "%d/%m/%Y",
                "%Y/%m/%d"
            ]
            
            for fmt in formats:
                try:
                    return datetime.strptime(date_value, fmt)
                except ValueError:
                    continue
        
        return None
    
    async def find_matching_documents(
        self, 
        target_identifiers: DocumentIdentifiers,
        candidate_documents: List[Document]
    ) -> List[Tuple[DocumentIdentifiers, float]]:
        """
        Find documents that potentially match the target document.
        
        Args:
            target_identifiers: Identifiers from the document to match
            candidate_documents: List of documents to search through
            
        Returns:
            List of (identifiers, match_score) tuples sorted by score
        """
        matches = []
        
        for doc in candidate_documents:
            if doc.id == target_identifiers.document_id:
                continue  # Don't match with self
            
            candidate_identifiers = await self.extract_document_identifiers(doc)
            match_score = self._calculate_match_score(target_identifiers, candidate_identifiers)
            
            if match_score > 0:
                matches.append((candidate_identifiers, match_score))
        
        # Sort by match score descending
        matches.sort(key=lambda x: x[1], reverse=True)
        return matches
    
    def _calculate_match_score(
        self, 
        target: DocumentIdentifiers, 
        candidate: DocumentIdentifiers
    ) -> float:
        """
        Calculate match score between two document identifier sets.
        
        Returns:
            Float between 0.0 and 1.0 indicating match confidence
        """
        score = 0.0
        max_score = 0.0
        
        # Identifier matching (highest weight)
        identifier_score, identifier_max = self._score_identifier_matches(target, candidate)
        score += identifier_score
        max_score += identifier_max
        
        # Address matching (medium weight)
        address_score, address_max = self._score_address_matches(target, candidate)
        score += address_score
        max_score += address_max
        
        # Temporal matching (lower weight)
        temporal_score, temporal_max = self._score_temporal_matches(target, candidate)
        score += temporal_score
        max_score += temporal_max
        
        # Return normalized score
        return score / max_score if max_score > 0 else 0.0
    
    def _score_identifier_matches(
        self, 
        target: DocumentIdentifiers, 
        candidate: DocumentIdentifiers
    ) -> Tuple[float, float]:
        """Score matches on identifiers (BOL, PRO, invoice numbers)."""
        score = 0.0
        max_score = 0.0
        
        # BOL number matches (highest priority)
        if target.bol_numbers and candidate.bol_numbers:
            max_score += 3.0
            if target.bol_numbers & candidate.bol_numbers:  # Exact match
                score += 3.0
            else:
                # Check fuzzy matches
                best_fuzzy = self._best_fuzzy_match(target.bol_numbers, candidate.bol_numbers)
                if best_fuzzy >= self.config.fuzzy_threshold:
                    score += 3.0 * best_fuzzy * self.config.fuzzy_match_weight
        
        # PRO number matches
        if target.pro_numbers and candidate.pro_numbers:
            max_score += 2.0
            if target.pro_numbers & candidate.pro_numbers:  # Exact match
                score += 2.0
            else:
                best_fuzzy = self._best_fuzzy_match(target.pro_numbers, candidate.pro_numbers)
                if best_fuzzy >= self.config.fuzzy_threshold:
                    score += 2.0 * best_fuzzy * self.config.fuzzy_match_weight
        
        # Invoice number matches
        if target.invoice_numbers and candidate.invoice_numbers:
            max_score += 1.5
            if target.invoice_numbers & candidate.invoice_numbers:
                score += 1.5
            else:
                best_fuzzy = self._best_fuzzy_match(target.invoice_numbers, candidate.invoice_numbers)
                if best_fuzzy >= self.config.fuzzy_threshold:
                    score += 1.5 * best_fuzzy * self.config.fuzzy_match_weight
        
        return score, max_score
    
    def _score_address_matches(
        self, 
        target: DocumentIdentifiers, 
        candidate: DocumentIdentifiers
    ) -> Tuple[float, float]:
        """Score matches on address information."""
        score = 0.0
        max_score = 0.0
        
        # Shipper name matching
        if target.shipper_name and candidate.shipper_name:
            max_score += 1.0
            similarity = self._calculate_string_similarity(target.shipper_name, candidate.shipper_name)
            if similarity >= self.config.name_similarity_threshold:
                score += similarity
        
        # Consignee name matching
        if target.consignee_name and candidate.consignee_name:
            max_score += 1.0
            similarity = self._calculate_string_similarity(target.consignee_name, candidate.consignee_name)
            if similarity >= self.config.name_similarity_threshold:
                score += similarity
        
        # Address matching
        if target.shipper_address and candidate.shipper_address:
            max_score += 0.5
            similarity = self._calculate_string_similarity(target.shipper_address, candidate.shipper_address)
            if similarity >= self.config.address_similarity_threshold:
                score += 0.5 * similarity
        
        if target.consignee_address and candidate.consignee_address:
            max_score += 0.5
            similarity = self._calculate_string_similarity(target.consignee_address, candidate.consignee_address)
            if similarity >= self.config.address_similarity_threshold:
                score += 0.5 * similarity
        
        return score, max_score
    
    def _score_temporal_matches(
        self, 
        target: DocumentIdentifiers, 
        candidate: DocumentIdentifiers
    ) -> Tuple[float, float]:
        """Score matches on temporal proximity."""
        score = 0.0
        max_score = 0.0
        
        # Check pickup/delivery date proximity
        target_dates = [d for d in [target.pickup_date, target.delivery_date, target.document_date] if d]
        candidate_dates = [d for d in [candidate.pickup_date, candidate.delivery_date, candidate.document_date] if d]
        
        if target_dates and candidate_dates:
            max_score += 1.0
            
            # Find closest date pair
            min_diff = float('inf')
            for t_date in target_dates:
                for c_date in candidate_dates:
                    diff_days = abs((t_date - c_date).days)
                    min_diff = min(min_diff, diff_days)
            
            # Score based on proximity
            if min_diff <= self.config.strict_date_window_days:
                score += 1.0
            elif min_diff <= self.config.max_date_difference_days:
                # Linear decay
                score += 1.0 * (1 - min_diff / self.config.max_date_difference_days)
        
        return score, max_score
    
    def _best_fuzzy_match(self, set1: Set[str], set2: Set[str]) -> float:
        """Find the best fuzzy match score between two sets of strings."""
        best_score = 0.0
        for s1 in set1:
            for s2 in set2:
                score = self._calculate_string_similarity(s1, s2)
                best_score = max(best_score, score)
        return best_score
    
    def _calculate_string_similarity(self, str1: str, str2: str) -> float:
        """Calculate similarity between two strings using SequenceMatcher."""
        if not str1 or not str2:
            return 0.0
        return SequenceMatcher(None, str1, str2).ratio()
    
    async def group_related_documents(
        self, 
        documents: List[Document]
    ) -> List[DocumentGroup]:
        """
        Group related documents based on matching scores.
        
        Args:
            documents: List of documents to group
            
        Returns:
            List of DocumentGroup objects
        """
        if not documents:
            return []
        
        # Extract identifiers for all documents
        logger.info(f"Extracting identifiers for {len(documents)} documents")
        document_identifiers = []
        for doc in documents:
            identifiers = await self.extract_document_identifiers(doc)
            document_identifiers.append(identifiers)
        
        # Create groups using clustering approach
        groups = []
        used_indices = set()
        
        for i, target in enumerate(document_identifiers):
            if i in used_indices:
                continue
            
            # Start new group with this document
            group = DocumentGroup(documents=[target])
            used_indices.add(i)
            
            # Find all documents that match this one
            for j, candidate in enumerate(document_identifiers):
                if j == i or j in used_indices:
                    continue
                
                match_score = self._calculate_match_score(target, candidate)
                
                if match_score >= self.config.review_threshold:
                    group.documents.append(candidate)
                    used_indices.add(j)
            
            # Calculate group metrics
            await self._calculate_group_metrics(group)
            groups.append(group)
        
        logger.info(f"Created {len(groups)} document groups")
        return groups
    
    async def _calculate_group_metrics(self, group: DocumentGroup) -> None:
        """Calculate confidence score and other metrics for a document group."""
        if not group.documents:
            return
        
        # Calculate overall confidence based on identifier overlap
        total_score = 0.0
        total_comparisons = 0
        match_reasons = []
        mismatch_flags = []
        
        # Compare each pair of documents in the group
        for i in range(len(group.documents)):
            for j in range(i + 1, len(group.documents)):
                doc1, doc2 = group.documents[i], group.documents[j]
                score = self._calculate_match_score(doc1, doc2)
                total_score += score
                total_comparisons += 1
                
                # Identify specific matches and mismatches
                await self._identify_match_reasons(doc1, doc2, score, match_reasons, mismatch_flags)
        
        # Calculate average confidence
        group.confidence_score = total_score / total_comparisons if total_comparisons > 0 else 0.0
        group.match_reasons = list(set(match_reasons))
        group.mismatch_flags = list(set(mismatch_flags))
        
        # Determine if review is needed
        group.needs_review = (
            group.confidence_score < self.config.medium_confidence_threshold or
            len(mismatch_flags) > 0 or
            len(group.documents) > 5  # Too many documents might indicate over-grouping
        )
        
        # Calculate completeness score
        document_types = {doc.document_type for doc in group.documents}
        required_present = len(document_types & self.config.required_document_types)
        preferred_present = len(document_types & self.config.preferred_document_types)
        
        group.completeness_score = (
            required_present / len(self.config.required_document_types) * 0.7 +
            preferred_present / len(self.config.preferred_document_types) * 0.3
        )
        
        # Extract dominant identifiers
        group.dominant_identifiers = self._extract_dominant_identifiers(group.documents)
        
        # Calculate date range
        all_dates = []
        for doc in group.documents:
            all_dates.extend([d for d in [doc.pickup_date, doc.delivery_date, doc.document_date] if d])
        
        if all_dates:
            group.date_range = (min(all_dates), max(all_dates))
        
        group.total_documents = len(group.documents)
        group.updated_at = datetime.now()
    
    async def _identify_match_reasons(
        self, 
        doc1: DocumentIdentifiers, 
        doc2: DocumentIdentifiers, 
        score: float,
        match_reasons: List[str],
        mismatch_flags: List[str]
    ) -> None:
        """Identify specific reasons for matches and mismatches."""
        
        # Identifier matches
        if doc1.bol_numbers & doc2.bol_numbers:
            match_reasons.append(f"BOL number match: {list(doc1.bol_numbers & doc2.bol_numbers)}")
        
        if doc1.pro_numbers & doc2.pro_numbers:
            match_reasons.append(f"PRO number match: {list(doc1.pro_numbers & doc2.pro_numbers)}")
        
        if doc1.invoice_numbers & doc2.invoice_numbers:
            match_reasons.append(f"Invoice number match: {list(doc1.invoice_numbers & doc2.invoice_numbers)}")
        
        # Address matches
        if (doc1.shipper_name and doc2.shipper_name and 
            self._calculate_string_similarity(doc1.shipper_name, doc2.shipper_name) >= self.config.name_similarity_threshold):
            match_reasons.append("Shipper name match")
        
        if (doc1.consignee_name and doc2.consignee_name and 
            self._calculate_string_similarity(doc1.consignee_name, doc2.consignee_name) >= self.config.name_similarity_threshold):
            match_reasons.append("Consignee name match")
        
        # Mismatches (conflicting information)
        if (doc1.shipper_name and doc2.shipper_name and 
            self._calculate_string_similarity(doc1.shipper_name, doc2.shipper_name) < 0.3):
            mismatch_flags.append("Conflicting shipper names")
        
        if (doc1.consignee_name and doc2.consignee_name and 
            self._calculate_string_similarity(doc1.consignee_name, doc2.consignee_name) < 0.3):
            mismatch_flags.append("Conflicting consignee names")
        
        # Date conflicts
        if doc1.pickup_date and doc2.delivery_date and doc1.pickup_date > doc2.delivery_date:
            mismatch_flags.append("Pickup date after delivery date")
        
        # Amount conflicts (large discrepancies)
        if (doc1.total_amount and doc2.total_amount and 
            abs(doc1.total_amount - doc2.total_amount) > max(doc1.total_amount, doc2.total_amount) * 0.5):
            mismatch_flags.append("Large amount discrepancy")
    
    def _extract_dominant_identifiers(self, documents: List[DocumentIdentifiers]) -> Dict[str, str]:
        """Extract the most common identifiers across all documents in a group."""
        
        # Count occurrences of each identifier
        bol_counts = {}
        pro_counts = {}
        
        for doc in documents:
            for bol in doc.bol_numbers:
                bol_counts[bol] = bol_counts.get(bol, 0) + 1
            for pro in doc.pro_numbers:
                pro_counts[pro] = pro_counts.get(pro, 0) + 1
        
        result = {}
        
        # Get most common identifiers
        if bol_counts:
            result["primary_bol"] = max(bol_counts.items(), key=lambda x: x[1])[0]
        
        if pro_counts:
            result["primary_pro"] = max(pro_counts.items(), key=lambda x: x[1])[0]
        
        # Get most common names
        shipper_names = [doc.shipper_name for doc in documents if doc.shipper_name]
        consignee_names = [doc.consignee_name for doc in documents if doc.consignee_name]
        
        if shipper_names:
            result["primary_shipper"] = max(set(shipper_names), key=shipper_names.count)
        
        if consignee_names:
            result["primary_consignee"] = max(set(consignee_names), key=consignee_names.count)
        
        return result
    
    async def save_document_groups(self, groups: List[DocumentGroup]) -> bool:
        """
        Save document groups to the database.
        
        Args:
            groups: List of DocumentGroup objects to save
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Save groups to a new table or update existing documents
            # This would involve creating a new table for document_groups
            # and potentially updating the documents table with group_id references
            
            logger.info(f"Saving {len(groups)} document groups to database")
            
            # For now, return True as this would require database schema changes
            # In a real implementation, this would:
            # 1. Create document_groups table with group metadata
            # 2. Create document_group_members table for document associations
            # 3. Update documents table with group_id references
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to save document groups: {e}")
            return False


# Module-level instance for dependency injection
document_matching_engine = DocumentMatchingEngine() 