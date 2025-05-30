"""
Redis Event Service for emitting events when loads are ready for invoicing.

This service uses the Upstash REST API for Redis operations, which is more
reliable for serverless environments and doesn't require TCP connections.

Key features:
- Emits invoice_ready events when POD is processed AND rate confirmation verified
- Uses Upstash REST API (https://endpoint.upstash.io) instead of Redis protocol
- Graceful degradation when Redis is unavailable (logs warnings, doesn't crash)
- HTTP-based communication for better serverless compatibility
"""

import json
import logging
import httpx
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Union
from uuid import UUID

from app.config.settings import settings

logger = logging.getLogger(__name__)


class RedisEventService:
    """
    Service for emitting events to Redis using Upstash REST API.
    
    Handles graceful degradation when Redis is unavailable - logs warnings
    but doesn't fail the main processing pipeline.
    """
    
    def __init__(self):
        """Initialize the Redis event service."""
        self.settings = settings
        self._redis_url = None
        self._redis_token = None
        self._client = None
        self._setup_client()
        
        # Event channel names
        self.INVOICE_READY_CHANNEL = "invoice_ready"
        
        # Connection retry settings
        self.RETRY_INTERVAL_SECONDS = 300  # 5 minutes
        
    def _setup_client(self):
        """Set up the HTTP client for Upstash REST API."""
        try:
            # Extract Redis URL and token from environment
            redis_url = self.settings.redis_url
            if not redis_url:
                logger.warning("Redis URL not configured - events will be disabled")
                return
            
            # Parse Upstash URL format: https://endpoint.upstash.io
            if redis_url.startswith('https://'):
                self._redis_url = redis_url
            else:
                logger.error(f"Invalid Redis URL format: {redis_url}. Expected https:// format for Upstash.")
                return
            
            # Use the REST token from settings
            self._redis_token = getattr(self.settings, 'redis_token', None)
            if not self._redis_token:
                logger.warning("Redis token not configured - events will be disabled")
                return
            
            # Create HTTP client
            self._client = httpx.Client(
                base_url=self._redis_url,
                headers={
                    'Authorization': f'Bearer {self._redis_token}',
                    'Content-Type': 'application/json'
                },
                timeout=5.0
            )
            
            logger.info("Redis event service initialized successfully with Upstash REST API")
            
        except Exception as e:
            logger.error(f"Failed to setup Redis client: {e}")
            self._client = None
    
    async def _execute_command(self, command: list) -> Optional[Any]:
        """Execute a Redis command using Upstash REST API."""
        if not self._client:
            logger.warning("Redis client not available - skipping command")
            return None
        
        try:
            response = self._client.post('', json=command)
            response.raise_for_status()
            result = response.json()
            return result.get('result')
        except Exception as e:
            logger.error(f"Redis command failed: {e}")
            return None
    
    async def emit_invoice_ready(self, load_id: str, driver_id: str) -> bool:
        """
        Emit an invoice_ready event to Redis.
        
        Args:
            load_id: The ID of the load that's ready for invoicing
            driver_id: The ID of the driver assigned to the load
            
        Returns:
            bool: True if event was emitted successfully, False otherwise
        """
        if not self._client:
            logger.warning("Redis not available - invoice_ready event not emitted")
            return False
        
        try:
            event_data = {
                'event_type': 'invoice_ready',
                'load_id': load_id,
                'driver_id': driver_id,
                'timestamp': datetime.utcnow().isoformat(),
                'source': 'ocrLoad'
            }
            
            # Publish to invoice_events channel
            channel = 'invoice_events'
            message = json.dumps(event_data)
            
            result = await self._execute_command(['PUBLISH', channel, message])
            
            if result is not None:
                logger.info(f"Invoice ready event emitted for load {load_id}, driver {driver_id}")
                return True
            else:
                logger.error(f"Failed to emit invoice ready event for load {load_id}")
                return False
                
        except Exception as e:
            logger.error(f"Error emitting invoice ready event for load {load_id}: {e}")
            return False
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Check Redis connection health.
        
        Returns:
            dict: Health check results
        """
        if not self._client:
            return {
                'status': 'unhealthy',
                'error': 'Redis client not initialized',
                'timestamp': datetime.utcnow().isoformat()
            }
        
        try:
            result = await self._execute_command(['PING'])
            
            if result == 'PONG':
                return {
                    'status': 'healthy',
                    'response_time_ms': 'N/A',  # Could add timing if needed
                    'timestamp': datetime.utcnow().isoformat()
                }
            else:
                return {
                    'status': 'unhealthy',
                    'error': f'Unexpected ping response: {result}',
                    'timestamp': datetime.utcnow().isoformat()
                }
                
        except Exception as e:
            return {
                'status': 'unhealthy',
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat()
            }
    
    def close(self):
        """Close the HTTP client."""
        if self._client:
            self._client.close()


# Global service instance
redis_event_service = RedisEventService() 