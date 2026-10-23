"""Unified Connector Contract for OrgBridge AI.

Defines the abstract BaseConnector base class for live event ingestion
and bidirectional write-backs with GitHub, Jira, and Slack.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from fastapi import Request


class BaseConnector(ABC):
    """Abstract interface defining required methods for enterprise connectors."""

    provider_name: str = "base"

    @abstractmethod
    async def verify_signature(self, request: Request, secret: Optional[str] = None) -> bytes:
        """Cryptographically verifies incoming webhook payload HMAC and replay tolerance.

        Returns raw body bytes if authentic. Raises HTTPException(401/413) on failure.
        """
        pass

    @abstractmethod
    def redact_payload(self, payload: Any) -> Any:
        """Pre-ingestion scrubber removing secrets, PII, and sensitive tokens from incoming payload."""
        pass

    @abstractmethod
    async def normalize_to_graph(self, payload: Dict[str, Any], tenant_graph: str) -> Dict[str, Any]:
        """Normalizes raw external payload into graph node/edge definitions and upserts to tenant graph."""
        pass

    @abstractmethod
    async def poll_delta(self, tenant_graph: str, cursor: Optional[str] = None) -> Dict[str, Any]:
        """Performs incremental cursor-based backfill / polling for changes since cursor."""
        pass

    @abstractmethod
    async def execute_writeback(self, action: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Executes transactional write-back action (e.g. create PR, link Jira Epic, post Slack card)."""
        pass
