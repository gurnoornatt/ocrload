#!/usr/bin/env python3
"""
Database migration script to add missing columns to documents table.

This script adds the columns needed for the media processing pipeline:
- type (document type enum)
- url (storage URL)
- status (processing status enum)
- updated_at (timestamp)
- metadata (JSONB for additional data)
"""

import asyncio
import logging

from app.services.supabase_client import supabase_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def migrate_documents_table():
    """Add missing columns to documents table."""

    client = supabase_service.client

    migrations = [
        # Add document type column
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                          WHERE table_name = 'documents' AND column_name = 'type') THEN
                -- Create enum type if it doesn't exist
                CREATE TYPE document_type AS ENUM ('CDL', 'COI', 'AGREEMENT', 'RATE_CON', 'POD');

                -- Add the column
                ALTER TABLE documents ADD COLUMN type document_type;
            END IF;
        END $$;
        """,
        # Add URL column
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                          WHERE table_name = 'documents' AND column_name = 'url') THEN
                ALTER TABLE documents ADD COLUMN url TEXT;
            END IF;
        END $$;
        """,
        # Add status column
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                          WHERE table_name = 'documents' AND column_name = 'status') THEN
                -- Create enum type if it doesn't exist
                CREATE TYPE document_status AS ENUM ('pending', 'parsed', 'needs_review', 'failed');

                -- Add the column with default value
                ALTER TABLE documents ADD COLUMN status document_status DEFAULT 'pending';
            END IF;
        END $$;
        """,
        # Add updated_at column
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                          WHERE table_name = 'documents' AND column_name = 'updated_at') THEN
                ALTER TABLE documents ADD COLUMN updated_at TIMESTAMPTZ DEFAULT NOW();
            END IF;
        END $$;
        """,
        # Add metadata column
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                          WHERE table_name = 'documents' AND column_name = 'metadata') THEN
                ALTER TABLE documents ADD COLUMN metadata JSONB DEFAULT '{}';
            END IF;
        END $$;
        """,
    ]

    for i, migration in enumerate(migrations, 1):
        try:
            logger.info(f"Running migration {i}/{len(migrations)}...")

            # Execute the migration using raw SQL
            client.rpc("exec_sql", {"sql": migration}).execute()

            logger.info(f"Migration {i} completed successfully")

        except Exception as e:
            logger.error(f"Migration {i} failed: {e}")
            # Try alternative approach using direct SQL execution
            try:
                # For Supabase, we might need to use a different approach
                logger.info(f"Trying alternative approach for migration {i}...")
                # This might not work with anon key, but let's try
                client.postgrest.rpc("exec_sql", {"sql": migration}).execute()
                logger.info(f"Migration {i} completed with alternative approach")
            except Exception as e2:
                logger.error(
                    f"Alternative approach also failed for migration {i}: {e2}"
                )
                logger.warning(
                    "You may need to run these migrations manually in the Supabase dashboard:"
                )
                logger.warning(migration)
                continue

    # Verify the migrations
    logger.info("Verifying migrations...")
    try:
        # Test that we can now select all expected columns
        (
            client.table("documents")
            .select(
                "id, driver_id, load_id, type, url, status, updated_at, metadata, parsed_data, confidence, verified, created_at"
            )
            .limit(1)
            .execute()
        )
        logger.info("✓ All columns are now accessible")

        # Show the current schema
        columns_to_test = [
            "id",
            "driver_id",
            "load_id",
            "type",
            "url",
            "status",
            "updated_at",
            "metadata",
            "parsed_data",
            "confidence",
            "verified",
            "created_at",
        ]
        existing_columns = []

        for col in columns_to_test:
            try:
                client.table("documents").select(col).limit(1).execute()
                existing_columns.append(col)
            except:
                pass

        logger.info(f"Current columns: {existing_columns}")

    except Exception as e:
        logger.error(f"Verification failed: {e}")


if __name__ == "__main__":
    asyncio.run(migrate_documents_table())
