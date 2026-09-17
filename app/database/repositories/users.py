"""Data-access layer for `User` rows."""
from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import User


class UserRepository:
    """Encapsulates all SQL touching the `users` table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, user_id: int) -> User | None:
        return await self._session.get(User, user_id)

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        result = await self._session.execute(select(User).where(User.telegram_id == telegram_id))
        return result.scalar_one_or_none()

    async def upsert_from_telegram(
        self,
        *,
        telegram_id: int,
        username: str | None,
        first_name: str | None,
        last_name: str | None,
        language: str | None = None,
    ) -> User:
        """Create the user if new, otherwise refresh their cached profile fields.

        Telegram users can change their username/name at any time, so we
        keep the local copy in sync on every interaction instead of trusting
        stale data.
        """
        user = await self.get_by_telegram_id(telegram_id)
        if user is None:
            user = User(
                telegram_id=telegram_id,
                username=username,
                first_name=first_name,
                last_name=last_name,
                language=language,
            )
            self._session.add(user)
            await self._session.flush()
            return user

        changed = False
        if user.username != username:
            user.username = username
            changed = True
        if user.first_name != first_name:
            user.first_name = first_name
            changed = True
        if user.last_name != last_name:
            user.last_name = last_name
            changed = True
        if changed:
            await self._session.flush()
        return user

    async def search(self, query: str, *, limit: int = 20) -> list[User]:
        """Search by first name, last name, username or telegram_id.

        A purely numeric query is matched against `telegram_id` in addition
        to the text fields, so admins can paste an ID straight from a
        participant card.
        """
        query = query.strip()
        like = f"%{query}%"
        conditions = [
            User.first_name.ilike(like),
            User.last_name.ilike(like),
            User.username.ilike(like),
        ]
        if query.lstrip("-").isdigit():
            conditions.append(User.telegram_id == int(query))

        stmt = select(User).where(or_(*conditions)).order_by(User.id).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def set_language(self, user: User, language: str) -> User:
        user.language = language
        await self._session.flush()
        return user
