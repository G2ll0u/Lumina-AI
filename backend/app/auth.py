from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv
load_dotenv()

_security = HTTPBearer(auto_error=False)

SECRET_KEY = os.getenv("SECRET_KEY", "")

async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_security)
) -> dict:
    """
    Validates a Bearer token against SECRET_KEY from .env.
    Set SECRET_KEY in your .env to enable authentication.
    If SECRET_KEY is empty, the endpoint is open (dev mode only).
    """
    if not SECRET_KEY:
        # Dev mode: no key set = open access (log a warning)
        print("[WARNING] SECRET_KEY is not set. API is open to all requests.")
        return {"sub": "anonymous", "roles": ["user"]}

    if credentials is None or credentials.credentials != SECRET_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return {"sub": "api-user", "roles": ["user"]}
