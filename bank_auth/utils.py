import datetime
from datetime import timezone

import jwt
import string
from secrets import choice
from config import settings
from bcrypt import gensalt, hashpw, checkpw

def hash_password(password: str) -> str:
    password_bytes = password.encode("utf-8")
    salt = gensalt()
    hashed_bytes = hashpw(password_bytes, salt)
    return hashed_bytes.decode("utf-8")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    plain_bytes = plain_password.encode("utf-8")
    hashed_bytes = hashed_password.encode("utf-8")
    return checkpw(plain_bytes, hashed_bytes)

def generate_otp() -> str:
    digits = string.digits
    return "".join(choice(digits) for _ in range(6))

def create_jwt_token(
        payload: dict,
        expires_delta: datetime.timedelta,
        is_refresh: bool = False
) -> str:
    to_encode = payload.copy()
    expire = datetime.datetime.now(timezone.utc) + expires_delta
    to_encode.update({
        "exp": expire,
        "type": "refresh" if is_refresh else "access"
    })

    return jwt.encode(to_encode, settings.private_key, algorithm="RS256")