from fastapi import HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings

# Define security scheme
security = HTTPBearer(auto_error=False)


async def verify_api_key(
    credentials: HTTPAuthorizationCredentials = Security(security),
):
    """
    Verify API key from Authorization header
    """
    # Skip authentication in development if API key is not set
    if not settings.API_KEY:
        return True

    if (
        not credentials
        or not credentials.credentials
        or credentials.credentials != settings.API_KEY
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )
    return True


async def verify_api_key_query(api_key: str | None = None):
    """
    Verify API key from query parameter
    Alternative method for clients that can't easily use Bearer tokens
    """
    # Skip authentication in development if API key is not set
    if not settings.API_KEY:
        return True

    if not api_key or api_key != settings.API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )
    return True
