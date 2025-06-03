"""Supabase client service for database and storage operations."""

import logging
from typing import Any
from uuid import UUID

from postgrest.exceptions import APIError
from supabase import Client, StorageException, create_client
from supabase.client import ClientOptions

from app.config.settings import settings
from app.models.database import Document, Driver, Load

logger = logging.getLogger(__name__)


class SupabaseService:
    """
    Service class for interacting with Supabase database and storage.

    Handles both sync and async operations with proper error handling,
    connection pooling, and timeout management.
    """

    def __init__(self):
        """Initialize the Supabase client with configuration."""
        self._client: Client | None = None
        self._initialized = False

        # Client options for timeout and connection management
        # Don't manually set auth headers - let Supabase client handle authentication
        self._client_options = ClientOptions(
            schema="public",
            auto_refresh_token=True,
            persist_session=True,
        )

        # Storage bucket name
        self.storage_bucket = settings.s3_bucket

    @property
    def client(self) -> Client:
        """Get the Supabase client, initializing if necessary."""
        if not self._client:
            self._initialize_client()
        return self._client

    def _initialize_client(self) -> None:
        """Initialize the Supabase client."""
        try:
            self._client = create_client(
                supabase_url=settings.supabase_url,
                supabase_key=settings.supabase_service_key
                or settings.supabase_anon_key,
                options=self._client_options,
            )
            self._initialized = True
            logger.info(
                f"Supabase client initialized successfully with {'service' if settings.supabase_service_key else 'anon'} key"
            )
        except Exception as e:
            logger.error(f"Failed to initialize Supabase client: {e}")
            raise

    async def health_check(self) -> dict[str, Any]:
        """
        Perform health check on database and storage.

        Returns:
            Dict with health status for database and storage

        Raises:
            Exception: If health check fails
        """
        health_status = {
            "database": {"status": "unknown", "message": ""},
            "storage": {"status": "unknown", "message": ""},
        }

        # Database health check
        try:
            # Simple query to test database connectivity
            self.client.table("drivers").select("id").limit(1).execute()
            health_status["database"] = {
                "status": "healthy",
                "message": "Database connection successful",
                "tables_accessible": True,
            }
            logger.debug("Database health check passed")
        except APIError as e:
            # Handle permission errors gracefully
            if "Invalid API key" in str(e) or "permission" in str(e).lower():
                health_status["database"] = {
                    "status": "limited",
                    "message": "Database accessible but with limited permissions (anon key)",
                }
                logger.warning(f"Database health check - permission limited: {e}")
            else:
                health_status["database"] = {
                    "status": "unhealthy",
                    "message": f"Database connection failed: {str(e)}",
                }
                logger.error(f"Database health check failed: {e}")
        except Exception as e:
            health_status["database"] = {
                "status": "unhealthy",
                "message": f"Database connection failed: {str(e)}",
            }
            logger.error(f"Database health check failed: {e}")

        # Storage health check
        try:
            # Test storage bucket access
            buckets = self.client.storage.list_buckets()
            bucket_exists = any(
                bucket.name == self.storage_bucket for bucket in buckets
            )

            if bucket_exists:
                # Test basic operations (list files)
                self.client.storage.from_(self.storage_bucket).list()
                health_status["storage"] = {
                    "status": "healthy",
                    "message": "Storage bucket accessible",
                    "bucket_name": self.storage_bucket,
                }
                logger.debug("Storage health check passed")
            else:
                health_status["storage"] = {
                    "status": "warning",
                    "message": f"Storage bucket '{self.storage_bucket}' not found - will be created when needed",
                }
        except Exception as e:
            health_status["storage"] = {
                "status": "unhealthy",
                "message": f"Storage access failed: {str(e)}",
            }
            logger.error(f"Storage health check failed: {e}")

        return health_status

    # Database Operations

    async def get_driver_by_id(self, driver_id: str | UUID) -> Driver | None:
        """Get driver by ID."""
        try:
            result = (
                self.client.table("drivers")
                .select("*")
                .eq("id", str(driver_id))
                .execute()
            )
            if result.data:
                return Driver(**result.data[0])
            return None
        except APIError as e:
            logger.error(f"Failed to get driver {driver_id}: {e}")
            raise

    async def get_load_by_id(self, load_id: str | UUID) -> Load | None:
        """Get load by ID."""
        try:
            result = (
                self.client.table("loads").select("*").eq("id", str(load_id)).execute()
            )
            if result.data:
                return Load(**result.data[0])
            return None
        except APIError as e:
            logger.error(f"Failed to get load {load_id}: {e}")
            raise

    async def create_document(self, document: Document) -> Document:
        """
        Create a new document record.

        Args:
            document: Document model instance

        Returns:
            Created document record as Document model
        """
        try:
            # Convert to dict and exclude computed fields
            document_data = document.model_dump(exclude={"created_at"})
            result = self.client.table("documents").insert(document_data).execute()
            return Document(**result.data[0])
        except APIError as e:
            logger.error(f"Failed to create document: {e}")
            raise

    async def create_document_raw(self, document_data: dict[str, Any]) -> Document:
        """
        Create a new document record from raw dictionary data.

        Args:
            document_data: Dictionary with document data (UUIDs as strings)

        Returns:
            Created document record as Document model
        """
        try:
            result = self.client.table("documents").insert(document_data).execute()
            return Document(**result.data[0])
        except APIError as e:
            logger.error(f"Failed to create document: {e}")
            raise

    async def create_invoice(self, invoice_data: dict[str, Any]) -> dict[str, Any] | None:
        """
        Create a new invoice record from parsed invoice data.

        Args:
            invoice_data: Dictionary with invoice data

        Returns:
            Created invoice record as dict or None if failed
        """
        try:
            logger.info(f"Creating invoice record for document: {invoice_data.get('document_id')}")
            result = self.client.table("invoices").insert(invoice_data).execute()
            if result.data:
                logger.info(f"Successfully created invoice record")
                return result.data[0]
            return None
        except APIError as e:
            logger.error(f"Failed to create invoice: {e}")
            # Don't raise here - let the caller handle the failure gracefully
            return None
        except Exception as e:
            logger.error(f"Unexpected error creating invoice: {e}")
            return None

    async def create_bol(self, bol_data: dict[str, Any]) -> dict[str, Any] | None:
        """
        Create a new Bill of Lading record from parsed BOL data.

        Args:
            bol_data: Dictionary with BOL data

        Returns:
            Created BOL record as dict or None if failed
        """
        try:
            logger.info(f"Creating BOL record for document: {bol_data.get('document_id')}")
            result = self.client.table("bills_of_lading").insert(bol_data).execute()
            if result.data:
                logger.info(f"Successfully created BOL record")
                return result.data[0]
            return None
        except APIError as e:
            logger.error(f"Failed to create BOL: {e}")
            # Don't raise here - let the caller handle the failure gracefully
            return None
        except Exception as e:
            logger.error(f"Unexpected error creating BOL: {e}")
            return None

    async def update_document(
        self, document_id: str | UUID, update_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Update document by ID."""
        try:
            result = (
                self.client.table("documents")
                .update(update_data)
                .eq("id", str(document_id))
                .execute()
            )
            return result.data[0] if result.data else None
        except APIError as e:
            logger.error(f"Failed to update document {document_id}: {e}")
            raise

    async def get_document_by_id(
        self, document_id: str | UUID
    ) -> Document | None:
        """Get document by ID."""
        try:
            result = (
                self.client.table("documents")
                .select("*")
                .eq("id", str(document_id))
                .execute()
            )
            if result.data:
                return Document(**result.data[0])
            return None
        except APIError as e:
            logger.error(f"Failed to get document {document_id}: {e}")
            raise

    async def update_driver_flags(self, driver_id: str | UUID, **flags) -> bool:
        """
        Update driver document flags.

        Args:
            driver_id: Driver UUID
            **flags: Flag names and values to update (e.g. cdl_verified=True)

        Returns:
            True if successful
        """
        try:
            # Get current driver
            driver = await self.get_driver_by_id(driver_id)
            if not driver:
                raise ValueError(f"Driver {driver_id} not found")

            # Update flags using the model method
            driver.update_doc_flags(**flags)

            result = (
                self.client.table("drivers")
                .update(
                    {
                        "doc_flags": driver.doc_flags.model_dump(),
                        "updated_at": driver.updated_at.isoformat(),
                    }
                )
                .eq("id", str(driver_id))
                .execute()
            )

            return len(result.data) > 0
        except APIError as e:
            logger.error(f"Failed to update driver flags for {driver_id}: {e}")
            raise

    async def update_load_status(self, load_id: str | UUID, status: str) -> bool:
        """Update load status."""
        try:
            result = (
                self.client.table("loads")
                .update({"status": status})
                .eq("id", str(load_id))
                .execute()
            )

            return len(result.data) > 0
        except APIError as e:
            logger.error(f"Failed to update load status for {load_id}: {e}")
            raise

    async def check_load_ratecon_verified(self, load_id: str | UUID) -> bool:
        """
        Check if load has rate confirmation verified.

        This checks for documents of type 'RATE_CON' with high confidence.
        """
        try:
            result = (
                self.client.table("documents")
                .select("confidence")
                .eq("load_id", str(load_id))
                .eq("type", "RATE_CON")
                .gte("confidence", 0.9)
                .execute()
            )

            return len(result.data) > 0
        except APIError as e:
            logger.error(f"Failed to check ratecon status for load {load_id}: {e}")
            return False

    # Storage Operations

    async def upload_file(
        self, file_path: str, file_content: bytes, content_type: str = None
    ) -> str:
        """
        Upload file to Supabase storage.

        Args:
            file_path: Path/name for the file in storage
            file_content: File content as bytes
            content_type: MIME type of the file

        Returns:
            Public URL of the uploaded file
        """
        try:
            # Prepare file options - only include content-type if provided
            file_options = {}
            if content_type:
                file_options["content-type"] = content_type

            # Upload file to storage bucket
            result = self.client.storage.from_(self.storage_bucket).upload(
                path=file_path,
                file=file_content,
                file_options=file_options if file_options else None,
            )

            if result:
                # Get public URL
                public_url = self.client.storage.from_(
                    self.storage_bucket
                ).get_public_url(file_path)
                logger.info(f"File uploaded successfully: {file_path}")
                return public_url
            else:
                raise StorageException("Upload failed - no response")

        except StorageException as e:
            logger.error(f"Failed to upload file {file_path}: {e}")
            raise

    async def delete_file(self, file_path: str) -> bool:
        """Delete file from storage."""
        try:
            result = self.client.storage.from_(self.storage_bucket).remove([file_path])
            return len(result) > 0
        except StorageException as e:
            logger.error(f"Failed to delete file {file_path}: {e}")
            return False

    async def get_signed_url(self, file_path: str, expires_in: int = 3600) -> str:
        """
        Get signed URL for private file access.

        Args:
            file_path: Path to file in storage
            expires_in: URL expiration time in seconds (default 1 hour)

        Returns:
            Signed URL for file access
        """
        try:
            result = self.client.storage.from_(self.storage_bucket).create_signed_url(
                path=file_path, expires_in=expires_in
            )
            return result.get("signedURL", "")
        except StorageException as e:
            logger.error(f"Failed to create signed URL for {file_path}: {e}")
            raise

    async def list_files(self, folder_path: str = "") -> list[dict[str, Any]]:
        """List files in storage bucket folder."""
        try:
            result = self.client.storage.from_(self.storage_bucket).list(folder_path)
            return result
        except StorageException as e:
            logger.error(f"Failed to list files in {folder_path}: {e}")
            raise


# Global service instance
supabase_service = SupabaseService()

# Convenience alias for backward compatibility
supabase_client = supabase_service
