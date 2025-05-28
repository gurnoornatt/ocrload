"""Integration tests for Supabase client with real database connection."""

import pytest
from app.services.supabase_client import supabase_service
from app.config.settings import settings


@pytest.mark.asyncio
@pytest.mark.integration
async def test_supabase_connection_real():
    """
    Test actual connection to Supabase database.
    
    This test requires valid SUPABASE_URL and either SUPABASE_SERVICE_KEY
    or SUPABASE_ANON_KEY environment variables to be set.
    """
    if not settings.supabase_url or not (settings.supabase_service_key or settings.supabase_anon_key):
        pytest.skip("Supabase credentials not configured")
    
    # Test health check with real connection
    health_status = await supabase_service.health_check()
    
    # Database should be accessible
    assert health_status["database"]["status"] == "healthy"
    assert "Database connection successful" in health_status["database"]["message"]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_existing_tables_accessible():
    """
    Test that we can access the existing tables in the database.
    
    Verifies that the tables (drivers, loads, documents, transactions) exist
    and are accessible without modifying any data.
    """
    if not settings.supabase_url or not (settings.supabase_service_key or settings.supabase_anon_key):
        pytest.skip("Supabase credentials not configured")
    
    # Test accessing drivers table
    try:
        # This should work even if table is empty
        result = supabase_service.client.table("drivers").select("id").limit(1).execute()
        assert result is not None
        print(f"Drivers table accessible, found {len(result.data)} records")
    except Exception as e:
        pytest.fail(f"Could not access drivers table: {e}")
    
    # Test accessing loads table
    try:
        result = supabase_service.client.table("loads").select("id").limit(1).execute()
        assert result is not None
        print(f"Loads table accessible, found {len(result.data)} records")
    except Exception as e:
        pytest.fail(f"Could not access loads table: {e}")
    
    # Test accessing documents table
    try:
        result = supabase_service.client.table("documents").select("id").limit(1).execute()
        assert result is not None
        print(f"Documents table accessible, found {len(result.data)} records")
    except Exception as e:
        pytest.fail(f"Could not access documents table: {e}")
    
    # Test accessing transactions table
    try:
        result = supabase_service.client.table("transactions").select("id").limit(1).execute()
        assert result is not None
        print(f"Transactions table accessible, found {len(result.data)} records")
    except Exception as e:
        pytest.fail(f"Could not access transactions table: {e}")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_storage_bucket_access():
    """
    Test that we can access the storage bucket.
    
    This test verifies storage functionality without uploading files.
    """
    if not settings.supabase_url or not (settings.supabase_service_key or settings.supabase_anon_key):
        pytest.skip("Supabase credentials not configured")
    
    # Test bucket listing
    try:
        buckets = supabase_service.client.storage.list_buckets()
        assert buckets is not None
        print(f"Found {len(buckets)} storage buckets")
        
        # Check if our target bucket exists
        bucket_names = [bucket.name for bucket in buckets]
        print(f"Available buckets: {bucket_names}")
        
        if settings.s3_bucket in bucket_names:
            # Test listing files in bucket (should work even if empty)
            files = supabase_service.client.storage.from_(settings.s3_bucket).list()
            print(f"Found {len(files)} files in {settings.s3_bucket} bucket")
        else:
            print(f"Target bucket '{settings.s3_bucket}' not found, available: {bucket_names}")
            
    except Exception as e:
        pytest.fail(f"Could not access storage: {e}")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_database_schema_structure():
    """
    Test that the database schema matches our expectations.
    
    Verifies the columns exist in the tables we need to work with.
    """
    if not settings.supabase_url or not (settings.supabase_service_key or settings.supabase_anon_key):
        pytest.skip("Supabase credentials not configured")
    
    # Test documents table structure
    try:
        # Try to select specific columns we need
        result = supabase_service.client.table("documents").select(
            "id, driver_id, load_id, type, url, confidence, parsed_data, verified"
        ).limit(1).execute()
        assert result is not None
        print("Documents table has expected column structure")
    except Exception as e:
        pytest.fail(f"Documents table structure issue: {e}")
    
    # Test drivers table structure  
    try:
        result = supabase_service.client.table("drivers").select(
            "id, phone_number, doc_flags, status"
        ).limit(1).execute()
        assert result is not None
        print("Drivers table has expected column structure")
    except Exception as e:
        pytest.fail(f"Drivers table structure issue: {e}")
    
    # Test loads table structure
    try:
        result = supabase_service.client.table("loads").select(
            "id, origin, destination, rate, assigned_driver_id, status"
        ).limit(1).execute()
        assert result is not None
        print("Loads table has expected column structure")
    except Exception as e:
        pytest.fail(f"Loads table structure issue: {e}") 