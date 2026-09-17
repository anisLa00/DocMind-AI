from sqlalchemy.ext.asyncio import AsyncSession

from src.models.user import User
from src.schemas.auth import LoginUserModel
from src.services.users import UserService
from src.utils.jwt import create_access_token, create_refresh_token
from src.utils.security import verify_password


class AuthService:
    async def authenticate(self, login_data: LoginUserModel, session: AsyncSession) -> User | None:
        user = await UserService().get_user_by_email(login_data.email, session)
        if user is None:
            return None
        if not verify_password(login_data.password, user.password_hash):
            return None
        if not user.is_active:
            return None
        return user

    async def login_user(
        self, login_data: LoginUserModel, session: AsyncSession
    ) -> dict[str, str] | None:
        user = await self.authenticate(login_data, session)
        if user is None:
            return None

        return {
            "access_token": create_access_token(user_id=str(user.id)),
            "refresh_token": create_refresh_token(user_id=str(user.id)),
            "token_type": "bearer",
        }
