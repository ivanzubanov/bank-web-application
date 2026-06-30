from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from bank_auth.utils import decode_jwt_token
from bank_auth.models import UserRole

security = HTTPBearer()

async def get_current_user_payload(
        credentials: HTTPAuthorizationCredentials = Depends(security)
) -> dict:
    token = credentials.credentials
    payload = await decode_jwt_token(token)
    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type. Access token required."
        )
    return payload

class RoleChecker:
    def __init__(self, allowed_roles: list[UserRole]):
        self.allowed_roles = allowed_roles

    async def __call__(self, payload: dict = Depends(get_current_user_payload)) -> dict:
        user_role = payload.get("role")
        if user_role not in [r.value for r in self.allowed_roles] and user_role not in self.allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )
        return payload