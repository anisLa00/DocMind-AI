from src.models.user import User
from pydantic import BaseModel,Field
import uuid
from datetime import datetime


class UserModel(BaseModel):
    id:uuid.UUID
    email:str
    first_name:str
    last_name:str
    password_hash:str = Field(exclude=True) 
    created_at:datetime 
    updated_at:datetime

class CreateUserModel(BaseModel):
    first_name:str= Field(max_length=20)
    last_name:str= Field(max_length=20)
    email:str =Field(max_length=50)
    password:str = Field(min_length=6)

class UpdateUserModel(BaseModel):
    first_name: str | None = Field(default=None, max_length=20)
    last_name: str | None = Field(default=None, max_length=20)
    email: str | None = Field(default=None, max_length=50)