"""로그인 유스케이스"""
from dataclasses import dataclass
from domain.exceptions import InvalidCredentialsError
from application.ports.user_repository import UserRepository


@dataclass
class LoginInput:
    email: str
    password: str


@dataclass
class LoginOutput:
    user_id: int
    email: str
    name: str
    role: str
    plan: str


class LoginUseCase:
    def __init__(self, user_repo: UserRepository, verify_password_fn):
        self._user_repo = user_repo
        self._verify_password = verify_password_fn

    async def execute(self, input: LoginInput) -> LoginOutput:
        user = await self._user_repo.get_by_email(input.email)
        if user is None:
            raise InvalidCredentialsError()
        if not self._verify_password(input.password, user.password_hash):
            raise InvalidCredentialsError()
        if not user.is_active:
            raise InvalidCredentialsError()
        await self._user_repo.update_last_login(user.id)
        return LoginOutput(user_id=user.id, email=user.email, name=user.name,
                           role=user.role, plan=user.plan)
