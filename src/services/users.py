from sqlalchemy.ext.asyncio import AsyncSession
from src.models.user import User
from src.schemas.users import CreateUserModel,UserModel,UpdateUserModel
from pwdlib import PasswordHash
from sqlalchemy import select
import uuid
from fastapi.exceptions import HTTPException

generate_password_hash=PasswordHash.recommended()

class UserService:
    async def create_user(self,user_data: CreateUserModel,session: AsyncSession):
       user_data_dict = user_data.model_dump()

       password = user_data_dict.pop("password")

       new_user = User(
               **user_data_dict
    )

       new_user.password_hash = generate_password_hash.hash(password)

       session.add(new_user)

       await session.commit()
       await session.refresh(new_user)

       return new_user
    
    async def get_user_by_email(self,email:str,session:AsyncSession):
        statement = select(User).where(User.email == email)

        result = await session.execute(statement)

        user = result.scalar_one_or_none()

        return user
    async def get_all_user(self,session:AsyncSession):
        statement=select(User).order_by(User.created_at)
        result= await session.execute(statement)

        return result.scalars().all()
    async def get_user_by_id(self,user_id:uuid.UUID,session:AsyncSession):
        statement = select(User).where(User.id==user_id)
        result= await session.execute(statement)
        return result.scalar_one_or_none()

    async def update_user(self,user_id: uuid.UUID,user_data: UpdateUserModel,session: AsyncSession):
        statement = select(User).where(User.id == user_id)

        result = await session.execute(statement)
        user = result.scalar_one_or_none()

        if user is None:
              raise HTTPException(
              status_code=404,
              detail="User not found"
        )

        update_data = user_data.model_dump(exclude_unset=True)

        for key, value in update_data.items():
            setattr(user, key, value)

        await session.commit()
        await session.refresh(user)

        return user

    async def delete_user(self,user_id: uuid.UUID,session: AsyncSession):
            statement = select(User).where(User.id == user_id)

            result = await session.execute(statement)

            user = result.scalar_one_or_none()

            if user is None:
               raise HTTPException(
               status_code=404,
               detail="User not found"
        )

            await session.delete(user)
            await session.commit()

            return user

