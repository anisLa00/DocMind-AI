import redis.asyncio as redis
from src.config import settings



redis_client= redis.from_url(
    settings.REDIS_URL,
    decode_responses=True
)
async def revoke_token(jti:str, expires_in:int):
    await redis_client.set(f"revoked:{jti}","1",ex=expires_in)


async def is_token_revoked(jti:str):
    value=await redis_client.get(f"revoked:{jti}")
    return value is not None    

