"""Postgres backed implementation of the storage facade."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from infra.db import async_session_factory, create_engine
from infra.db.repositories import (
    PostgresAthletesRepo,
    PostgresCoachesRepo,
    PostgresRecordsRepo,
    PostgresResultsRepo,
)
from sprint_bot.application.ports.repositories import AthletesRepo, CoachesRepo, RecordsRepo, ResultsRepo
from sprint_bot.application.ports.storage import Storage


class PostgresStorage(Storage):
    """Storage facade powered by Postgres and SQLAlchemy."""

    def __init__(self, *, database_url: str) -> None:
        self._database_url = database_url
        self._engine: AsyncEngine | None = None
        self._session_factory: async_sessionmaker[AsyncSession] | None = None
        self._athletes_repo: PostgresAthletesRepo | None = None
        self._coaches_repo: PostgresCoachesRepo | None = None
        self._results_repo: PostgresResultsRepo | None = None
        self._records_repo: PostgresRecordsRepo | None = None

    async def init(self) -> None:
        self._engine = create_engine(self._database_url)
        self._session_factory = async_session_factory(self._engine)
        self._athletes_repo = PostgresAthletesRepo(self._session_factory)
        self._coaches_repo = PostgresCoachesRepo(self._session_factory)
        self._results_repo = PostgresResultsRepo(self._session_factory)
        self._records_repo = PostgresRecordsRepo(self._session_factory)

    async def close(self) -> None:
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None
            self._session_factory = None
        self._athletes_repo = None
        self._coaches_repo = None
        self._results_repo = None
        self._records_repo = None

    @property
    def athletes(self) -> AthletesRepo:
        if self._athletes_repo is None:
            raise RuntimeError("Storage not initialised")
        return self._athletes_repo

    @property
    def coaches(self) -> CoachesRepo:
        if self._coaches_repo is None:
            raise RuntimeError("Storage not initialised")
        return self._coaches_repo

    @property
    def results(self) -> ResultsRepo:
        if self._results_repo is None:
            raise RuntimeError("Storage not initialised")
        return self._results_repo

    @property
    def records(self) -> RecordsRepo:
        if self._records_repo is None:
            raise RuntimeError("Storage not initialised")
        return self._records_repo

    @property
    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        if self._session_factory is None:
            raise RuntimeError("Storage not initialised")
        return self._session_factory

    @property
    def engine(self) -> AsyncEngine:
        if self._engine is None:
            raise RuntimeError("Storage not initialised")
        return self._engine
