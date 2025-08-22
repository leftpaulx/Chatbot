from snowflake.snowpark import Session
from app.core.config import settings
from app.core.security import encode_private_key, generate_jwt_token
import asyncio
import time

# In-memory token cache per-process
_JWT_LOCK = asyncio.Lock()
_JWT = {'token': None, 'exp': 0}

p_key, pkb = encode_private_key(settings.PRIVATE_KEY)


def snowflake_session():
    """
    Create a Snowflake session
    Args:
        pkb: bytes - The private key in DER format
        snowflake_account: str - The Snowflake account
        snowflake_user: str - The Snowflake user
    Returns:
        session: snowflake.snowpark.Session - The Snowflake session
    """
    conn_params = { 
        'account': settings.SNOWFLAKE_ACCOUNT,
        'user': settings.SNOWFLAKE_PROJECT_USER,
        'authenticator': 'SNOWFLAKE_JWT',
        'private_key': pkb
    }
    session = Session.builder.configs(conn_params).create() 
    return session

async def get_jwt_cached_async() -> str:   # caching the jwt token
    """
    Get a JWT token and cache it
    Args:
        p_key: cryptography.hazmat.primitives.asymmetric.rsa.RSAPrivateKey - The private key
        account: str - The Snowflake account
        user: str - The Snowflake user
    Returns:
        token: str - The JWT token
    """
    now = int(time.time())
    if _JWT["token"] and (_JWT["exp"] - now) > 120: # 120 seconds margin
        return _JWT["token"]
    async with _JWT_LOCK:
        now = int(time.time())
        if _JWT["token"] and (_JWT["exp"] - now) > 120: # 120 seconds margin
            return _JWT["token"]
        token, exp = generate_jwt_token(p_key, settings.SNOWFLAKE_ACCOUNT, settings.SNOWFLAKE_PROJECT_USER)
        _JWT["token"], _JWT["exp"] = token, exp
        return token