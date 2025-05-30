# Test Documents Folder

This folder is for placing real document samples to test the OCR and parsing pipeline.

## Needed Documents for Integration Testing

Please place the following document types in this folder:

### 1. POD (Proof of Delivery) Documents
- **Filename**: `sample_pod.pdf` or `sample_pod.jpg`
- **Contents**: Should contain delivery confirmation, signatures, dates
- **Purpose**: Test POD parsing and invoice_ready event emission

### 2. Bill of Lading Documents  
- **Filename**: `sample_bol.pdf` or `sample_bol.jpg`
- **Contents**: Shipping document with origin/destination, weights, commodities
- **Purpose**: Test Bill of Lading parsing workflow

### 3. Rate Confirmation Documents
- **Filename**: `sample_ratecon.pdf` or `sample_ratecon.jpg`  
- **Contents**: Rate confirmation with pickup/delivery dates, rates
- **Purpose**: Test rate confirmation parsing and ratecon_verified flag

### 4. CDL Documents
- **Filename**: `sample_cdl.pdf` or `sample_cdl.jpg`
- **Contents**: Commercial driver's license with license number, expiration
- **Purpose**: Test CDL verification workflow

### 5. COI (Certificate of Insurance) Documents
- **Filename**: `sample_coi.pdf` or `sample_coi.jpg`
- **Contents**: Insurance certificate with policy numbers, coverage amounts
- **Purpose**: Test insurance verification workflow

### 6. Agreement Documents
- **Filename**: `sample_agreement.pdf` or `sample_agreement.jpg`
- **Contents**: Signed contract or agreement document
- **Purpose**: Test agreement parsing and signature detection

## File Formats Supported
- PDF files (preferred)
- JPEG/JPG images
- PNG images

## Usage in Tests
These documents will be used by integration tests to verify the complete processing pipeline:
1. Upload → OCR → Parse → Database → Events
2. Error handling and retry logic
3. API mocking scenarios
4. End-to-end workflow validation

## Privacy Note
Do not commit any real/sensitive documents. Use sanitized or sample documents only. 