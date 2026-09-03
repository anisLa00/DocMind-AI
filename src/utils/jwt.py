from datetime import datetime, timedelta, timezone
from fastapi.exceptions import HTTPException

import jwt
import uuid

from src.config import settings


def create_access_token(user_id:str , refresh:bool=False ):
        expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
        payload ={}

        payload["user"]= user_id
        payload["exp"] = expire
        payload["jti"] =str(uuid.uuid4())
        payload["refresh"]=refresh


        token= jwt.encode(
                payload=payload,
                key=settings.SECRET_KEY,
                algorithm=settings.ALGORITHM
        )
        return token
def decode_token(token:str):
        try:    
            payload = jwt.decode(token,settings.SECRET_KEY,algorithms=[settings.ALGORITHM])
            return payload

        except jwt.InvalidTokenError:
               raise HTTPException(
                      status_code=401,
                      detail="Inavlis or expired token"
               )