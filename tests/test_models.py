"""Tests for database models and validation logic."""

import pytest
from datetime import datetime, timezone
from uuid import UUID, uuid4
from pydantic import ValidationError

from app.models.database import (
    Document, Driver, Load, Transaction,
    DocumentType, DocumentStatus, DriverStatus, LoadStatus,
    DocumentFlags, LoadFlags,
    CDLData, COIData, AgreementData, RateConData, PODData,
    DocumentCreateRequest, DocumentProcessingResponse, ParseTestRequest,
    HealthCheckResponse, ServiceHealthStatus
)


class TestDocumentModels:
    """Test cases for document-related models."""
    
    def test_document_type_enum(self):
        """Test DocumentType enum values."""
        assert DocumentType.CDL == "CDL"
        assert DocumentType.COI == "COI"
        assert DocumentType.AGREEMENT == "AGREEMENT"
        assert DocumentType.RATE_CON == "RATE_CON"
        assert DocumentType.POD == "POD"
    
    def test_document_flags_creation(self):
        """Test DocumentFlags model creation and defaults."""
        flags = DocumentFlags()
        assert flags.cdl_verified is False
        assert flags.insurance_verified is False
        assert flags.agreement_signed is False
        
        # Test with custom values
        flags = DocumentFlags(cdl_verified=True, insurance_verified=True)
        assert flags.cdl_verified is True
        assert flags.insurance_verified is True
        assert flags.agreement_signed is False  # default
    
    def test_load_flags_creation(self):
        """Test LoadFlags model creation."""
        flags = LoadFlags()
        assert flags.ratecon_verified is False
        assert flags.pod_completed is False
        
        flags = LoadFlags(ratecon_verified=True)
        assert flags.ratecon_verified is True
        assert flags.pod_completed is False


class TestParsedDataModels:
    """Test cases for parsed document data models."""
    
    def test_cdl_data_date_parsing(self):
        """Test CDL expiration date parsing from various formats."""
        # MM/DD/YYYY format
        cdl = CDLData(expiration_date="12/25/2025")
        assert cdl.expiration_date == datetime(2025, 12, 25)
        
        # MM-DD-YYYY format
        cdl = CDLData(expiration_date="03-15-2024")
        assert cdl.expiration_date == datetime(2024, 3, 15)
        
        # YYYY-MM-DD format (ISO format works)
        cdl = CDLData(expiration_date="2026-06-30")
        assert cdl.expiration_date == datetime(2026, 6, 30)
        
        # Two-digit year
        cdl = CDLData(expiration_date="12/31/25")
        assert cdl.expiration_date == datetime(2025, 12, 31)
        
        # Invalid date should raise validation error
        with pytest.raises(ValidationError):
            CDLData(expiration_date="invalid-date")
        
        # None should remain None
        cdl = CDLData(expiration_date=None)
        assert cdl.expiration_date is None
    
    def test_coi_data_currency_parsing(self):
        """Test COI currency amount parsing."""
        # Dollar amounts with symbols
        coi = COIData(
            general_liability_amount="$1,000,000",
            auto_liability_amount="$500,000"
        )
        assert coi.general_liability_amount == 100000000  # $1M in cents
        assert coi.auto_liability_amount == 50000000     # $500K in cents
        
        # Plain numbers
        coi = COIData(general_liability_amount="250000")
        assert coi.general_liability_amount == 25000000  # $250K in cents
        
        # Float amounts
        coi = COIData(general_liability_amount="100000.50")
        assert coi.general_liability_amount == 10000050  # $100K.50 in cents
        
        # Invalid amounts
        coi = COIData(general_liability_amount="invalid")
        assert coi.general_liability_amount is None
    
    def test_rate_con_data_rate_parsing(self):
        """Test rate confirmation rate parsing."""
        # Dollar amount with formatting
        rate_con = RateConData(rate_amount="$2,500")
        assert rate_con.rate_amount == 250000  # $2500 in cents
        
        # Plain number
        rate_con = RateConData(rate_amount="1500")
        assert rate_con.rate_amount == 150000  # $1500 in cents
        
        # Float amount
        rate_con = RateConData(rate_amount="1250.75")
        assert rate_con.rate_amount == 125075  # $1250.75 in cents


class TestDatabaseModels:
    """Test cases for main database models."""
    
    def test_document_creation(self):
        """Test Document model creation and validation."""
        driver_id = uuid4()
        doc = Document(
            driver_id=driver_id,
            type=DocumentType.CDL,
            url="https://storage.example.com/doc.jpg",
            confidence=0.95
        )
        
        assert doc.driver_id == driver_id
        assert doc.type == DocumentType.CDL
        assert doc.url == "https://storage.example.com/doc.jpg"
        assert doc.confidence == 0.95
        assert isinstance(doc.id, UUID)
        assert isinstance(doc.created_at, datetime)
    
    def test_document_requires_association(self):
        """Test that document requires either driver_id or load_id."""
        with pytest.raises(ValidationError) as exc_info:
            Document(
                type=DocumentType.CDL,
                url="https://storage.example.com/doc.jpg"
            )
        assert "Document must have either driver_id or load_id" in str(exc_info.value)
    
    def test_document_confidence_validation(self):
        """Test confidence score validation."""
        # Valid confidence
        doc = Document(
            driver_id=uuid4(),
            type=DocumentType.CDL,
            url="https://storage.example.com/doc.jpg",
            confidence=0.75
        )
        assert doc.confidence == 0.75
        
        # Confidence above 1.0 should be clamped during validation
        doc = Document(
            driver_id=uuid4(),
            type=DocumentType.CDL,
            url="https://storage.example.com/doc.jpg",
            confidence=1.5
        )
        assert doc.confidence == 1.0
        
        # Confidence below 0.0 should be clamped
        doc = Document(
            driver_id=uuid4(),
            type=DocumentType.CDL,
            url="https://storage.example.com/doc.jpg",
            confidence=-0.1
        )
        assert doc.confidence == 0.0
    
    def test_document_get_parsed_data_typed(self):
        """Test getting typed parsed data."""
        # CDL document
        doc = Document(
            driver_id=uuid4(),
            type=DocumentType.CDL,
            url="https://storage.example.com/doc.jpg",
            parsed_data={
                "driver_name": "John Doe",
                "license_number": "DL123456",
                "expiration_date": "12/31/2025"
            }
        )
        
        parsed = doc.get_parsed_data_typed()
        assert isinstance(parsed, CDLData)
        assert parsed.driver_name == "John Doe"
        assert parsed.license_number == "DL123456"
        
        # No parsed data
        doc.parsed_data = None
        assert doc.get_parsed_data_typed() is None
        
        # Invalid parsed data - CDLData allows None values so it creates an empty object
        doc.parsed_data = {"invalid": "data"}
        parsed = doc.get_parsed_data_typed()
        assert isinstance(parsed, CDLData)
        assert parsed.driver_name is None
    
    def test_driver_creation(self):
        """Test Driver model creation and validation."""
        driver = Driver(phone_number="+1234567890")
        
        assert driver.phone_number == "+1234567890"
        assert driver.language == "English"  # default
        assert driver.status == DriverStatus.PENDING  # default
        assert isinstance(driver.doc_flags, DocumentFlags)
        assert driver.doc_flags.cdl_verified is False
        assert isinstance(driver.id, UUID)
    
    def test_driver_phone_validation(self):
        """Test phone number validation."""
        # Valid phone numbers
        Driver(phone_number="1234567890")
        Driver(phone_number="+1-234-567-8900")
        Driver(phone_number="(123) 456-7890")
        
        # Invalid phone number (too short)
        with pytest.raises(ValidationError):
            Driver(phone_number="123456")
    
    def test_driver_update_doc_flags(self):
        """Test updating driver document flags."""
        driver = Driver(phone_number="1234567890")
        original_updated_at = driver.updated_at
        
        # Update flags
        driver.update_doc_flags(cdl_verified=True, insurance_verified=True)
        
        assert driver.doc_flags.cdl_verified is True
        assert driver.doc_flags.insurance_verified is True
        assert driver.doc_flags.agreement_signed is False  # unchanged
        assert driver.updated_at > original_updated_at
    
    def test_load_creation(self):
        """Test Load model creation."""
        load = Load(
            origin="Atlanta, GA",
            destination="Chicago, IL",
            rate=250000  # $2500 in cents
        )
        
        assert load.origin == "Atlanta, GA"
        assert load.destination == "Chicago, IL"
        assert load.rate == 250000
        assert load.status == LoadStatus.AVAILABLE  # default
    
    def test_load_rate_validation(self):
        """Test load rate validation."""
        # Valid rates
        Load(rate=250000)
        Load(rate=0)
        Load(rate=None)
        
        # Invalid negative rate
        with pytest.raises(ValidationError):
            Load(rate=-1000)
    
    def test_load_rate_conversion(self):
        """Test load rate conversion methods."""
        load = Load(rate=250000)  # $2500 in cents
        
        # Get rate in dollars
        assert load.get_rate_in_dollars() == 2500.0
        
        # Set rate from dollars
        load.set_rate_from_dollars(3750.50)
        assert load.rate == 375050  # $3750.50 in cents
        
        # No rate set
        load.rate = None
        assert load.get_rate_in_dollars() is None
    
    def test_transaction_creation(self):
        """Test Transaction model creation."""
        driver_id = uuid4()
        transaction = Transaction(
            driver_id=driver_id,
            amount=250000,  # $2500 in cents
            type="payment"
        )
        
        assert transaction.driver_id == driver_id
        assert transaction.amount == 250000
        assert transaction.type == "payment"
        assert transaction.status == "pending"  # default
    
    def test_transaction_amount_validation(self):
        """Test transaction amount validation."""
        driver_id = uuid4()
        
        # Valid amounts
        Transaction(driver_id=driver_id, amount=0, type="payment")
        Transaction(driver_id=driver_id, amount=100000, type="payment")
        
        # Invalid negative amount
        with pytest.raises(ValidationError):
            Transaction(driver_id=driver_id, amount=-1000, type="payment")


class TestRequestResponseModels:
    """Test cases for API request/response models."""
    
    def test_document_create_request(self):
        """Test DocumentCreateRequest validation."""
        driver_id = uuid4()
        
        # Valid request with driver_id
        request = DocumentCreateRequest(
            driver_id=driver_id,
            doc_type=DocumentType.CDL,
            media_url="https://example.com/media.jpg"
        )
        assert request.driver_id == driver_id
        assert request.load_id is None
        
        # Valid request with load_id
        load_id = uuid4()
        request = DocumentCreateRequest(
            load_id=load_id,
            doc_type=DocumentType.RATE_CON,
            media_url="https://example.com/media.pdf"
        )
        assert request.load_id == load_id
        assert request.driver_id is None
        
        # Invalid request (no IDs)
        with pytest.raises(ValidationError) as exc_info:
            DocumentCreateRequest(
                doc_type=DocumentType.CDL,
                media_url="https://example.com/media.jpg"
            )
        assert "Either driver_id or load_id must be provided" in str(exc_info.value)
    
    def test_document_processing_response(self):
        """Test DocumentProcessingResponse model."""
        doc_id = uuid4()
        response = DocumentProcessingResponse(
            success=True,
            doc_id=doc_id,
            confidence=0.95,
            flags={
                "cdl_verified": True,
                "insurance_verified": False,
                "agreement_signed": False,
                "ratecon_verified": False,
                "pod_completed": False
            },
            processing_time_ms=2500
        )
        
        assert response.success is True
        assert response.doc_id == doc_id
        assert response.confidence == 0.95
        assert response.needs_retry is False  # default
        assert response.flags["cdl_verified"] is True
        assert response.processing_time_ms == 2500
    
    def test_parse_test_request_path_validation(self):
        """Test ParseTestRequest path security validation."""
        # Valid local paths
        ParseTestRequest(path="./test_file.jpg", doc_type=DocumentType.CDL)
        ParseTestRequest(path="/app/test_file.jpg", doc_type=DocumentType.CDL)
        ParseTestRequest(path="test_file.jpg", doc_type=DocumentType.CDL)
        
        # Invalid paths (directory traversal)
        with pytest.raises(ValidationError):
            ParseTestRequest(path="../etc/passwd", doc_type=DocumentType.CDL)
        
        with pytest.raises(ValidationError):
            ParseTestRequest(path="/etc/passwd", doc_type=DocumentType.CDL)


class TestHealthCheckModels:
    """Test cases for health check models."""
    
    def test_service_health_status(self):
        """Test ServiceHealthStatus model."""
        status = ServiceHealthStatus(
            status="healthy",
            message="Database connection active",
            details={"connections": 5, "latency_ms": 12}
        )
        
        assert status.status == "healthy"
        assert status.message == "Database connection active"
        assert status.details["connections"] == 5
    
    def test_health_check_response(self):
        """Test HealthCheckResponse model."""
        checks = {
            "database": ServiceHealthStatus(status="healthy", message="Connected"),
            "storage": ServiceHealthStatus(status="warning", message="Bucket missing")
        }
        
        response = HealthCheckResponse(
            ok=True,
            status="degraded",
            timestamp=datetime.now(timezone.utc),
            service="ocr-service",
            version="1.0.0",
            environment="development",
            checks=checks,
            response_time_ms=45.2
        )
        
        assert response.ok is True
        assert response.status == "degraded"
        assert response.service == "ocr-service"
        assert len(response.checks) == 2
        assert response.checks["database"].status == "healthy"
        assert response.checks["storage"].status == "warning"


class TestModelSerialization:
    """Test model serialization and JSON encoding."""
    
    def test_document_json_encoding(self):
        """Test Document model JSON serialization."""
        driver_id = uuid4()
        doc = Document(
            driver_id=driver_id,
            type=DocumentType.CDL,
            url="https://storage.example.com/doc.jpg",
            confidence=0.95
        )
        
        # Test model_dump includes all fields
        data = doc.model_dump()
        assert data["driver_id"] == driver_id  # UUID object preserved in model_dump
        assert data["type"] == "CDL"
        assert data["url"] == "https://storage.example.com/doc.jpg"
        assert data["confidence"] == 0.95
        assert "id" in data
        assert "created_at" in data
    
    def test_driver_flags_serialization(self):
        """Test driver document flags serialization."""
        driver = Driver(phone_number="1234567890")
        driver.update_doc_flags(cdl_verified=True)
        
        data = driver.model_dump()
        assert data["doc_flags"]["cdl_verified"] is True
        assert data["doc_flags"]["insurance_verified"] is False
        assert data["doc_flags"]["agreement_signed"] is False
    
    def test_load_rate_serialization(self):
        """Test load model with rate conversion."""
        load = Load(rate=250000)  # $2500 in cents
        
        data = load.model_dump()
        assert data["rate"] == 250000
        
        # Test rate conversion method
        assert load.get_rate_in_dollars() == 2500.0 