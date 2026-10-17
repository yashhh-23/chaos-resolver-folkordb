"""Authentication and Role-Based Access Control (RBAC) for OrgBridge AI API.

Provides security dependencies to protect sensitive and state-mutating endpoints:
- Read endpoints: Requires authenticated session with 'read' role.
- Mutation endpoints: Requires authenticated session with explicit 'write' authorization role.
- Destructive operations (reset_demo): Requires explicit 'admin' role.
"""

from typing import Set, Optional
from pydantic import BaseModel
from fastapi import Security, HTTPException, status, Depends
from fastapi.security import APIKeyHeader, HTTPBearer, HTTPAuthorizationCredentials
from src.config import settings
from src.utils.logger import logger


class UserSession(BaseModel):
    user_id: str
    roles: Set[str]


# Security Schemes
api_key_header_scheme = APIKeyHeader(name="X-API-Key", auto_error=False)
admin_key_header_scheme = APIKeyHeader(name="X-Admin-Key", auto_error=False)
bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    api_key: Optional[str] = Security(api_key_header_scheme),
    admin_key: Optional[str] = Security(admin_key_header_scheme),
    bearer: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
) -> UserSession:
    """Authenticates the caller and constructs a UserSession with associated roles."""
    token = None
    if bearer and bearer.credentials:
        token = bearer.credentials.strip()
    elif api_key:
        token = api_key.strip()

    admin_token = admin_key.strip() if admin_key else None

    # Check for Admin access first
    if (admin_token and admin_token == settings.admin_api_key) or (token and token == settings.admin_api_key):
        return UserSession(user_id="admin_operator", roles={"read", "write", "admin"})

    # Check for Standard Write / Operator access
    if token and token == settings.api_key:
        return UserSession(user_id="operator", roles={"read", "write"})

    # In development or testing environment, allow default dev key
    if settings.environment.lower() in ("development", "test", "testing"):
        if token in ("dev-key", "test-key", "orgbridge-war-room-2026"):
            return UserSession(user_id="dev_operator", roles={"read", "write"})
        if admin_token in ("dev-admin-key", "test-admin-key", "orgbridge-admin-war-room-2026"):
            return UserSession(user_id="dev_admin", roles={"read", "write", "admin"})

    logger.warning("Unauthenticated request blocked: missing or invalid API key / Bearer token.")
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required. Please provide a valid 'X-API-Key', 'X-Admin-Key', or 'Authorization: Bearer <token>' header.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_role(required_role: str):
    """Factory creating dependency to enforce required RBAC role."""
    def dependency(user: UserSession = Depends(get_current_user)) -> UserSession:
        if required_role not in user.roles and "admin" not in user.roles:
            logger.warning(f"Access denied for user '{user.user_id}': missing required role '{required_role}' (has: {user.roles})")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Forbidden: '{required_role}' authorization role is required for this operation.",
            )
        return user

    return dependency


require_read = require_role("read")
require_write = require_role("write")
require_admin = require_role("admin")
