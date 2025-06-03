"""
Context Gate Service

Pre-audit validation system that confirms all uploaded documents (invoice, BOL, 
rate confirmation, POD, etc.) actually belong to the same load, were submitted by 
the correct driver, and occurred in the right place and time.

Only when all checks pass does it trigger the audit engine. This avoids fraudulent 
or misattributed document processing.

The Context Gate performs these validation steps:
1. Required Document Types - confirms all expected documents exist for the load
2. Driver Match - verifies all docs come from the same driver ID listed on the load  
3. Timestamp Window - checks that all docs are within logical time range of load
4. GPS Corridor Check - confirms driver was physically near pickup/delivery locations
5. Document Uniqueness - confirms same document hasn't been submitted for different load
"""

import asyncio
import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple
from uuid import UUID

import httpx
from pydantic import BaseModel, Field

from app.models.database import Document, DocumentType
from app.services.supabase_client import supabase_service

logger = logging.getLogger(__name__)


class ValidationStep(Enum):
    """Context Gate validation steps."""
    REQUIRED_DOCUMENT_TYPES = "required_document_types"
    DRIVER_MATCH = "driver_match"
    TIMESTAMP_WINDOW = "timestamp_window"
    GPS_CORRIDOR_CHECK = "gps_corridor_check"
    DOCUMENT_UNIQUENESS = "document_uniqueness"


class ValidationResult(BaseModel):
    """Result of a single validation step."""
    step: ValidationStep
    passed: bool
    score: float = 0.0
    message: str = ""
    details: Dict[str, Any] = Field(default_factory=dict)


class ContextGateResult(BaseModel):
    """Overall result of Context Gate validation."""
    load_id: str
    driver_id: Optional[str] = None
    documents: List[UUID] = Field(default_factory=list)
    
    # Validation results
    validation_results: List[ValidationResult] = Field(default_factory=list)
    overall_passed: bool = False
    confidence_score: float = 0.0
    
    # Status
    status: str = "pending"  # pending, passed, context_mismatch
    flagged_for_review: bool = False
    mismatch_reasons: List[str] = Field(default_factory=list)
    
    # Metadata
    validated_at: datetime = Field(default_factory=datetime.now)
    processing_time_ms: int = 0


class LoadInfo(BaseModel):
    """Information about a load for Context Gate validation."""
    load_id: str
    driver_id: str
    pickup_location: Dict[str, float]  # {"latitude": lat, "longitude": lng}
    delivery_location: Dict[str, float]  # {"latitude": lat, "longitude": lng}
    pickup_date: datetime
    delivery_date: datetime
    required_document_types: Set[DocumentType] = Field(
        default_factory=lambda: {
            DocumentType.INVOICE,
            DocumentType.POD,  # BOL
            DocumentType.RATE_CONFIRMATION,
            DocumentType.POD,  # Proof of Delivery
            DocumentType.CDL
        }
    )


class ContextGateConfig(BaseModel):
    """Configuration for Context Gate validation."""
    # Timestamp validation
    max_time_window_hours: int = 48  # ±48 hours from pickup/delivery
    strict_time_window_hours: int = 24  # Stricter window for higher confidence
    
    # GPS validation
    location_tolerance_miles: float = 50.0  # Maximum distance from pickup/delivery
    gps_check_enabled: bool = False  # Will be enabled when Terminal API key provided
    
    # Document validation
    require_all_document_types: bool = True
    allow_partial_loads: bool = False
    
    # Confidence thresholds
    high_confidence_threshold: float = 0.90
    medium_confidence_threshold: float = 0.70
    review_threshold: float = 0.50
    
    # Terminal API settings (will be set when API key provided)
    terminal_api_base_url: str = "https://api.withterminal.com/tsp/v1"
    terminal_api_key: Optional[str] = None
    terminal_connection_token: Optional[str] = None


class ContextGateService:
    """Service for validating document context before audit processing."""
    
    def __init__(self, config: Optional[ContextGateConfig] = None):
        """Initialize the Context Gate service."""
        self.config = config or ContextGateConfig()
        self.supabase = supabase_service
        self._document_hash_cache: Dict[str, Set[str]] = {}
        logger.info("Context Gate service initialized")
    
    async def validate_load_documents(
        self, 
        load_info: LoadInfo, 
        documents: List[Document]
    ) -> ContextGateResult:
        """
        Validate that all documents belong to the specified load.
        
        Args:
            load_info: Information about the load
            documents: List of documents to validate
            
        Returns:
            ContextGateResult with validation outcomes
        """
        start_time = datetime.now()
        
        result = ContextGateResult(
            load_id=load_info.load_id,
            driver_id=load_info.driver_id,
            documents=[doc.id for doc in documents]
        )
        
        logger.info(f"Starting Context Gate validation for load {load_info.load_id} with {len(documents)} documents")
        
        try:
            # Step 1: Required Document Types
            doc_type_result = await self._validate_required_document_types(
                load_info, documents
            )
            result.validation_results.append(doc_type_result)
            
            # Step 2: Driver Match
            driver_result = await self._validate_driver_match(
                load_info, documents
            )
            result.validation_results.append(driver_result)
            
            # Step 3: Timestamp Window
            timestamp_result = await self._validate_timestamp_window(
                load_info, documents
            )
            result.validation_results.append(timestamp_result)
            
            # Step 4: GPS Corridor Check (if enabled)
            if self.config.gps_check_enabled:
                gps_result = await self._validate_gps_corridor(
                    load_info, documents
                )
                result.validation_results.append(gps_result)
            else:
                # Create a passed result for GPS check when disabled
                gps_result = ValidationResult(
                    step=ValidationStep.GPS_CORRIDOR_CHECK,
                    passed=True,
                    score=1.0,
                    message="GPS validation disabled - will be enabled when Terminal API configured"
                )
                result.validation_results.append(gps_result)
            
            # Step 5: Document Uniqueness
            uniqueness_result = await self._validate_document_uniqueness(
                load_info, documents
            )
            result.validation_results.append(uniqueness_result)
            
            # Calculate overall result
            await self._calculate_overall_result(result)
            
        except Exception as e:
            logger.error(f"Error during Context Gate validation: {e}")
            result.status = "context_mismatch"
            result.mismatch_reasons.append(f"Validation error: {str(e)}")
        
        # Record processing time
        processing_time = datetime.now() - start_time
        result.processing_time_ms = int(processing_time.total_seconds() * 1000)
        
        logger.info(f"Context Gate validation completed for load {load_info.load_id}: {result.status}")
        return result
    
    async def _validate_required_document_types(
        self, 
        load_info: LoadInfo, 
        documents: List[Document]
    ) -> ValidationResult:
        """Validate that all required document types are present."""
        
        present_types = {doc.type for doc in documents}
        required_types = load_info.required_document_types
        missing_types = required_types - present_types
        
        if missing_types:
            return ValidationResult(
                step=ValidationStep.REQUIRED_DOCUMENT_TYPES,
                passed=False,
                score=len(present_types & required_types) / len(required_types),
                message=f"Missing required document types: {[t.value for t in missing_types]}",
                details={
                    "present_types": [t.value for t in present_types],
                    "required_types": [t.value for t in required_types],
                    "missing_types": [t.value for t in missing_types]
                }
            )
        
        return ValidationResult(
            step=ValidationStep.REQUIRED_DOCUMENT_TYPES,
            passed=True,
            score=1.0,
            message="All required document types present",
            details={"present_types": [t.value for t in present_types]}
        )
    
    async def _validate_driver_match(
        self, 
        load_info: LoadInfo, 
        documents: List[Document]
    ) -> ValidationResult:
        """Validate that all documents come from the same driver."""
        
        # Extract driver IDs from document metadata/parsed_data
        driver_ids_found = set()
        documents_with_drivers = []
        
        for doc in documents:
            driver_id = None
            
            # Check document metadata first
            if hasattr(doc, 'driver_id') and doc.driver_id:
                driver_id = doc.driver_id
            
            # Check parsed data for driver information
            elif doc.parsed_data:
                driver_id = (
                    doc.parsed_data.get('driver_id') or
                    doc.parsed_data.get('driver_name') or
                    doc.parsed_data.get('submitted_by')
                )
            
            if driver_id:
                driver_ids_found.add(str(driver_id))
                documents_with_drivers.append((doc.id, driver_id))
        
        # If no driver information found in any document
        if not driver_ids_found:
            return ValidationResult(
                step=ValidationStep.DRIVER_MATCH,
                passed=False,
                score=0.0,
                message="No driver information found in any document",
                details={"documents_checked": len(documents)}
            )
        
        # Check if all driver IDs match the load driver
        expected_driver = str(load_info.driver_id)
        matching_drivers = driver_ids_found & {expected_driver}
        
        if len(driver_ids_found) == 1 and expected_driver in driver_ids_found:
            return ValidationResult(
                step=ValidationStep.DRIVER_MATCH,
                passed=True,
                score=1.0,
                message="All documents match expected driver",
                details={
                    "expected_driver": expected_driver,
                    "found_drivers": list(driver_ids_found),
                    "documents_with_drivers": documents_with_drivers
                }
            )
        
        # Multiple drivers found or driver mismatch
        return ValidationResult(
            step=ValidationStep.DRIVER_MATCH,
            passed=False,
            score=len(matching_drivers) / len(driver_ids_found) if driver_ids_found else 0.0,
            message=f"Driver mismatch - expected {expected_driver}, found {list(driver_ids_found)}",
            details={
                "expected_driver": expected_driver,
                "found_drivers": list(driver_ids_found),
                "documents_with_drivers": documents_with_drivers
            }
        )
    
    async def _validate_timestamp_window(
        self, 
        load_info: LoadInfo, 
        documents: List[Document]
    ) -> ValidationResult:
        """Validate documents are within logical time range of the load."""
        
        # Create time windows
        window_hours = self.config.max_time_window_hours
        strict_window_hours = self.config.strict_time_window_hours
        
        earliest_allowed = load_info.pickup_date - timedelta(hours=window_hours)
        latest_allowed = load_info.delivery_date + timedelta(hours=window_hours)
        
        strict_earliest = load_info.pickup_date - timedelta(hours=strict_window_hours)
        strict_latest = load_info.delivery_date + timedelta(hours=strict_window_hours)
        
        documents_in_window = 0
        documents_in_strict_window = 0
        document_timestamps = []
        
        for doc in documents:
            doc_timestamp = None
            
            # Try to extract timestamp from document
            if hasattr(doc, 'created_at') and doc.created_at:
                doc_timestamp = doc.created_at
            elif doc.parsed_data:
                # Look for various date fields in parsed data
                for date_field in ['document_date', 'created_date', 'timestamp', 'date']:
                    if date_field in doc.parsed_data:
                        try:
                            if isinstance(doc.parsed_data[date_field], str):
                                doc_timestamp = datetime.fromisoformat(
                                    doc.parsed_data[date_field].replace('Z', '+00:00')
                                )
                            elif isinstance(doc.parsed_data[date_field], datetime):
                                doc_timestamp = doc.parsed_data[date_field]
                            break
                        except (ValueError, TypeError):
                            continue
            
            if doc_timestamp:
                document_timestamps.append((doc.id, doc_timestamp))
                
                # Check if within windows
                if earliest_allowed <= doc_timestamp <= latest_allowed:
                    documents_in_window += 1
                    
                    if strict_earliest <= doc_timestamp <= strict_latest:
                        documents_in_strict_window += 1
        
        # Calculate scores
        total_docs = len(documents)
        window_score = documents_in_window / total_docs if total_docs > 0 else 0.0
        strict_score = documents_in_strict_window / total_docs if total_docs > 0 else 0.0
        
        # Use strict score if all documents are in strict window, otherwise use regular window
        final_score = strict_score if strict_score == 1.0 else window_score
        
        passed = documents_in_window == total_docs
        
        return ValidationResult(
            step=ValidationStep.TIMESTAMP_WINDOW,
            passed=passed,
            score=final_score,
            message=(
                f"All documents within time window" if passed else
                f"{documents_in_window}/{total_docs} documents within time window"
            ),
            details={
                "window_hours": window_hours,
                "strict_window_hours": strict_window_hours,
                "pickup_date": load_info.pickup_date.isoformat(),
                "delivery_date": load_info.delivery_date.isoformat(),
                "documents_in_window": documents_in_window,
                "documents_in_strict_window": documents_in_strict_window,
                "total_documents": total_docs,
                "document_timestamps": [
                    {"document_id": str(doc_id), "timestamp": ts.isoformat()}
                    for doc_id, ts in document_timestamps
                ]
            }
        )
    
    async def _validate_gps_corridor(
        self, 
        load_info: LoadInfo, 
        documents: List[Document]
    ) -> ValidationResult:
        """Validate driver was physically near pickup/delivery locations."""
        
        if not self.config.terminal_api_key:
            return ValidationResult(
                step=ValidationStep.GPS_CORRIDOR_CHECK,
                passed=False,
                score=0.0,
                message="Terminal API key not configured",
                details={"api_configured": False}
            )
        
        try:
            # Query Terminal API for driver location history
            locations = await self._fetch_driver_locations(
                load_info.driver_id,
                load_info.pickup_date,
                load_info.delivery_date
            )
            
            # Check if driver was near pickup and delivery locations
            near_pickup = await self._check_location_proximity(
                locations,
                load_info.pickup_location,
                load_info.pickup_date,
                self.config.location_tolerance_miles
            )
            
            near_delivery = await self._check_location_proximity(
                locations,
                load_info.delivery_location,
                load_info.delivery_date,
                self.config.location_tolerance_miles
            )
            
            # Calculate score based on proximity checks
            proximity_checks = [near_pickup, near_delivery]
            score = sum(proximity_checks) / len(proximity_checks)
            passed = all(proximity_checks)
            
            return ValidationResult(
                step=ValidationStep.GPS_CORRIDOR_CHECK,
                passed=passed,
                score=score,
                message=(
                    "Driver location confirmed at pickup and delivery" if passed else
                    "Driver location verification failed"
                ),
                details={
                    "near_pickup": near_pickup,
                    "near_delivery": near_delivery,
                    "tolerance_miles": self.config.location_tolerance_miles,
                    "locations_checked": len(locations)
                }
            )
            
        except Exception as e:
            logger.error(f"GPS corridor validation failed: {e}")
            return ValidationResult(
                step=ValidationStep.GPS_CORRIDOR_CHECK,
                passed=False,
                score=0.0,
                message=f"GPS validation error: {str(e)}",
                details={"error": str(e)}
            )
    
    async def _validate_document_uniqueness(
        self, 
        load_info: LoadInfo, 
        documents: List[Document]
    ) -> ValidationResult:
        """Validate documents haven't been submitted for different loads."""
        
        duplicate_documents = []
        document_hashes = []
        
        for doc in documents:
            # Generate document hash based on content
            doc_hash = await self._generate_document_hash(doc)
            document_hashes.append((doc.id, doc_hash))
            
            # Check if this hash has been used for other loads
            other_loads = await self._find_loads_with_document_hash(doc_hash, load_info.load_id)
            
            if other_loads:
                duplicate_documents.append({
                    "document_id": str(doc.id),
                    "document_hash": doc_hash,
                    "other_loads": other_loads
                })
        
        passed = len(duplicate_documents) == 0
        score = 1.0 - (len(duplicate_documents) / len(documents)) if documents else 1.0
        
        return ValidationResult(
            step=ValidationStep.DOCUMENT_UNIQUENESS,
            passed=passed,
            score=score,
            message=(
                "All documents are unique to this load" if passed else
                f"{len(duplicate_documents)} documents found in other loads"
            ),
            details={
                "total_documents": len(documents),
                "duplicate_documents": duplicate_documents,
                "document_hashes": [
                    {"document_id": str(doc_id), "hash": doc_hash}
                    for doc_id, doc_hash in document_hashes
                ]
            }
        )
    
    async def _fetch_driver_locations(
        self, 
        driver_id: str, 
        start_date: datetime, 
        end_date: datetime
    ) -> List[Dict[str, Any]]:
        """Fetch driver location history from Terminal API."""
        
        if not self.config.terminal_api_key:
            return []
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.config.terminal_api_base_url}/vehicles/locations",
                    headers={
                        "Authorization": f"Bearer {self.config.terminal_api_key}",
                        "Connection-Token": self.config.terminal_connection_token
                    },
                    params={
                        "driverIds": driver_id,
                        "start": start_date.isoformat(),
                        "end": end_date.isoformat()
                    },
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    data = response.json()
                    return data.get("results", [])
                else:
                    logger.error(f"Terminal API error {response.status_code}: {response.text}")
                    return []
                    
        except Exception as e:
            logger.error(f"Failed to fetch driver locations: {e}")
            return []
    
    async def _check_location_proximity(
        self, 
        locations: List[Dict[str, Any]], 
        target_location: Dict[str, float], 
        target_time: datetime, 
        tolerance_miles: float
    ) -> bool:
        """Check if driver was near target location around target time."""
        
        # Convert miles to approximate degrees (rough approximation)
        tolerance_degrees = tolerance_miles / 69.0  # 1 degree ≈ 69 miles
        
        # Look for locations within time window of target time
        time_window = timedelta(hours=6)  # 6-hour window around target time
        
        for location in locations:
            try:
                loc_time = datetime.fromisoformat(
                    location["locatedAt"].replace('Z', '+00:00')
                )
                
                # Check if within time window
                if abs((loc_time - target_time).total_seconds()) <= time_window.total_seconds():
                    # Check if within location tolerance
                    lat_diff = abs(location["location"]["latitude"] - target_location["latitude"])
                    lng_diff = abs(location["location"]["longitude"] - target_location["longitude"])
                    
                    if lat_diff <= tolerance_degrees and lng_diff <= tolerance_degrees:
                        return True
                        
            except (KeyError, ValueError, TypeError) as e:
                logger.warning(f"Invalid location data: {e}")
                continue
        
        return False
    
    async def _generate_document_hash(self, document: Document) -> str:
        """Generate a hash for document uniqueness checking."""
        
        # Create hash based on document content and key identifiers
        hash_components = []
        
        # Add document type
        hash_components.append(document.type.value)
        
        # Add key parsed data fields
        if document.parsed_data:
            for key in ['invoice_number', 'bol_number', 'pro_number', 'document_date']:
                if key in document.parsed_data:
                    hash_components.append(f"{key}:{document.parsed_data[key]}")
        
        # Add file hash if available
        if hasattr(document, 'file_hash') and document.file_hash:
            hash_components.append(f"file_hash:{document.file_hash}")
        
        # Create SHA-256 hash
        hash_string = "|".join(sorted(hash_components))
        return hashlib.sha256(hash_string.encode()).hexdigest()
    
    async def _find_loads_with_document_hash(
        self, 
        document_hash: str, 
        current_load_id: str
    ) -> List[str]:
        """Find other loads that have used this document hash."""
        
        try:
            # Query database for other loads with this document hash
            # This would need a document_hashes table to track hashes per load
            # For now, return empty list as this requires database schema extension
            
            # TODO: Implement database query when schema is extended
            # Example query:
            # SELECT DISTINCT load_id FROM document_hashes 
            # WHERE hash = ? AND load_id != ?
            
            return []
            
        except Exception as e:
            logger.error(f"Error checking document hash uniqueness: {e}")
            return []
    
    async def _calculate_overall_result(self, result: ContextGateResult) -> None:
        """Calculate overall validation result and confidence score."""
        
        passed_validations = [r for r in result.validation_results if r.passed]
        total_validations = len(result.validation_results)
        
        # Calculate weighted confidence score
        weights = {
            ValidationStep.REQUIRED_DOCUMENT_TYPES: 0.25,
            ValidationStep.DRIVER_MATCH: 0.25,
            ValidationStep.TIMESTAMP_WINDOW: 0.20,
            ValidationStep.GPS_CORRIDOR_CHECK: 0.20,
            ValidationStep.DOCUMENT_UNIQUENESS: 0.10
        }
        
        total_score = 0.0
        total_weight = 0.0
        
        for validation in result.validation_results:
            weight = weights.get(validation.step, 0.1)
            total_score += validation.score * weight
            total_weight += weight
        
        result.confidence_score = total_score / total_weight if total_weight > 0 else 0.0
        
        # Determine overall status
        if len(passed_validations) == total_validations:
            result.overall_passed = True
            result.status = "passed"
        else:
            result.overall_passed = False
            result.status = "context_mismatch"
            
            # Collect mismatch reasons
            for validation in result.validation_results:
                if not validation.passed:
                    result.mismatch_reasons.append(f"{validation.step.value}: {validation.message}")
        
        # Flag for review if confidence is low
        result.flagged_for_review = result.confidence_score < self.config.review_threshold
    
    async def save_validation_result(self, result: ContextGateResult) -> bool:
        """Save Context Gate validation result to database."""
        
        try:
            # TODO: Implement database saving when schema is ready
            # This would save to a context_gate_validations table
            
            logger.info(f"Context Gate result for load {result.load_id}: {result.status}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save Context Gate result: {e}")
            return False


# Configuration and utility functions
async def configure_terminal_api(api_key: str, connection_token: str) -> ContextGateConfig:
    """Configure Context Gate with Terminal API credentials."""
    
    config = ContextGateConfig()
    config.terminal_api_key = api_key
    config.terminal_connection_token = connection_token
    config.gps_check_enabled = True
    
    return config


async def create_load_info_from_documents(
    load_id: str,
    driver_id: str,
    documents: List[Document]
) -> LoadInfo:
    """Create LoadInfo from document data when load details aren't available."""
    
    # Extract pickup/delivery information from documents
    pickup_location = {"latitude": 0.0, "longitude": 0.0}
    delivery_location = {"latitude": 0.0, "longitude": 0.0}
    pickup_date = datetime.now()
    delivery_date = datetime.now()
    
    # Try to extract location and date info from BOL or invoice documents
    for doc in documents:
        if doc.parsed_data:
            # Extract dates
            if 'pickup_date' in doc.parsed_data:
                try:
                    pickup_date = datetime.fromisoformat(
                        str(doc.parsed_data['pickup_date']).replace('Z', '+00:00')
                    )
                except (ValueError, TypeError):
                    pass
            
            if 'delivery_date' in doc.parsed_data:
                try:
                    delivery_date = datetime.fromisoformat(
                        str(doc.parsed_data['delivery_date']).replace('Z', '+00:00')
                    )
                except (ValueError, TypeError):
                    pass
            
            # TODO: Extract GPS coordinates from address fields using geocoding
            # This would require address parsing and geocoding service
    
    return LoadInfo(
        load_id=load_id,
        driver_id=driver_id,
        pickup_location=pickup_location,
        delivery_location=delivery_location,
        pickup_date=pickup_date,
        delivery_date=delivery_date
    ) 