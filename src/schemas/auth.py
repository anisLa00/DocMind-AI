from pydantic import BaseModel, EmailStr, Field


class LoginUserModel(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class LoginResponseModel(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LogoutModel(BaseModel):
    refresh_token: str
    access_token: str | None = None
