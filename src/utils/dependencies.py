from fastapi import Depends
from fastapi.security import HTTPBearer
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from src.db.database import get_session
from src.utils.jwt import decode_token
from fastapi import HTTPException
from src.services.users import UserService
import uuid
from src.utils.redis import revoke_token
from fastapi import Request
from src.utils.redis import is_token_revoked
from datetime import datetime,timezone



class AccessTokenBearer(HTTPBearer):
    async def __call__(self, request:Request):
        credentials=await super().__call__(request)

        token= credentials.credentials
        token_data=decode_token(token)

        

        if token_data["refresh"]:
            raise HTTPException(
                status_code=401,
                detail="access token required"
            )
        if await is_token_revoked(token_data["jti"]):
                    raise HTTPException(
                        status_code=401,
                        detail="Refresh has been rekoved"
                    )
        
        return token_data

    
async def get_current_user(
    token_data: dict = Depends(AccessTokenBearer()),
    session: AsyncSession = Depends(get_session)
):
    user_id = uuid.UUID(token_data["user"])

    user = await UserService().get_user_by_id(
        user_id,
        session
    )

    return user   
class RefreshTokenBearer(HTTPBearer):

    async def __call__(self, request: Request):
        credentials = await super().__call__(request)

        token = credentials.credentials
        token_data = decode_token(token)
        if await is_token_revoked(token_data["jti"]):
            raise HTTPException(
                status_code=401,
                detail="Refresh has been rekoved"
            )
        if not token_data["refresh"]:
            raise HTTPException(status_code=401,detail="refresh token required")

        return token_data 

async def revoke_token_data(token_data: dict):
    jti = token_data["jti"]
    exp = token_data["exp"]

    expires_in = int(
        exp - datetime.now(timezone.utc).timestamp()
    )

    await revoke_token(
        jti=jti,
        expires_in=expires_in
    )    
    
