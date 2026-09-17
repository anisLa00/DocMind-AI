import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.user import User
from src.schemas.users import CreateUserModel, UpdateUserModel
from src.utils.errors import ConflictError, NotFoundError, ValidationError
from src.utils.security import hash_password, verify_password


class UserService:
    async def create_user(self, user_data: CreateUserModel, session: AsyncSession) -> User:
        email = user_data.email.lower()

        if await self.get_user_by_email(email, session) is not None:
            raise ConflictError("A user with this email already exists")

        new_user = User(
            email=email,
            first_name=user_data.first_name,
            last_name=user_data.last_name,
            password_hash=hash_password(user_data.password),
        )

        session.add(new_user)
        try:
            await session.commit()
        except IntegrityError:
            # Lost the race against a concurrent signup with the same email.
            await session.rollback()
            raise ConflictError("A user with this email already exists") from None

        await session.refresh(new_user)
        return new_user

    async def get_user_by_email(self, email: str, session: AsyncSession) -> User | None:
        result = await session.execute(select(User).where(User.email == email.lower()))
        return result.scalar_one_or_none()

    async def get_user_by_id(self, user_id: uuid.UUID, session: AsyncSession) -> User | None:
        result = await session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_all_users(
        self, session: AsyncSession, limit: int = 50, offset: int = 0
    ) -> Sequence[User]:
        statement = select(User).order_by(User.created_at).limit(limit).offset(offset)
        result = await session.execute(statement)
        return result.scalars().all()

    async def count_users(self, session: AsyncSession) -> int:
        result = await session.execute(select(func.count()).select_from(User))
        return int(result.scalar_one())

    async def update_user(
        self, user_id: uuid.UUID, user_data: UpdateUserModel, session: AsyncSession
    ) -> User:
        user = await self.get_user_by_id(user_id, session)
        if user is None:
            raise NotFoundError("User not found")

        update_data = user_data.model_dump(exclude_unset=True, exclude_none=True)

        new_email = update_data.get("email")
        if new_email:
            new_email = new_email.lower()
            update_data["email"] = new_email
            existing = await self.get_user_by_email(new_email, session)
            if existing is not None and existing.id != user.id:
                raise ConflictError("A user with this email already exists")

        for key, value in update_data.items():
            setattr(user, key, value)

        await session.commit()
        await session.refresh(user)
        return user

    async def change_password(
        self,
        user: User,
        current_password: str,
        new_password: str,
        session: AsyncSession,
    ) -> User:
        if not verify_password(current_password, user.password_hash):
            raise ValidationError("Current password is incorrect")

        user.password_hash = hash_password(new_password)
        await session.commit()
        await session.refresh(user)
        return user

    async def delete_user(self, user_id: uuid.UUID, session: AsyncSession) -> User:
        user = await self.get_user_by_id(user_id, session)
        if user is None:
            raise NotFoundError("User not found")

        await session.delete(user)
        await session.commit()
        return user
