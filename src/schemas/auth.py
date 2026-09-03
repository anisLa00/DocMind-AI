from pydantic import BaseModel,Field



class LoginUserModel(BaseModel):
    email:str=Field(max_length=50)
    password:str=Field(max_length=10)

class LoginResponseModel(BaseModel):
    access_token: str
    refresh_token:str
    token_type: str = "bearer" 

class LogoutModel(BaseModel):
    refresh_token:str
    access_token:str | None = None      