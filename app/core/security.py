import base64, hashlib, time, jwt
from cryptography.hazmat.primitives import serialization


def encode_private_key(key:str):
    """
    Encode the private key to DER format
    Args:
        key: str - The private key in PEM format
    Returns:
        p_key: cryptography.hazmat.primitives.asymmetric.rsa.RSAPrivateKey - The private key
        pkb: bytes - The private key in DER format
    """
    key=base64.b64decode(key).decode("utf-8")
    p_key= serialization.load_pem_private_key(
    key.encode("utf-8"),
    password=None
    )   
    pkb = p_key.private_bytes(
    encoding=serialization.Encoding.DER,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption())
    return p_key, pkb

def generate_jwt_token(p_key,snowflake_acount:str,snowflake_user:str):
    """
    Generate a JWT token
    Args:
        p_key: cryptography.hazmat.primitives.asymmetric.rsa.RSAPrivateKey - The private key
        snowflake_acount: str - The Snowflake account
        snowflake_user: str - The Snowflake user
    Returns:
        jwt_token: str - The JWT token
    """
    pub_der = p_key.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    fp = "SHA256:" + base64.b64encode(hashlib.sha256(pub_der).digest()).decode()
    now = int(time.time())
    exp = now + 59 * 60   # <= 1 hour
    payload = {
        "iss": f"{snowflake_acount}.{snowflake_user}.{fp}",
        "sub": f"{snowflake_acount}.{snowflake_user}",
        "iat": now,
        "exp": exp   # <= 1 hour
    }
    return jwt.encode(payload, p_key, algorithm="RS256"), exp

