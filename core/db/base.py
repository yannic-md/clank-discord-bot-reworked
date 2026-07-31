from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from core.dotenv_setup import DB_NAME, DB_URL


class Base(DeclarativeBase):
    """Base model class for SQLAlchemy Object-Relational Mapping (ORM).

    Inheriting from `DeclarativeBase` establishes a unified registry and metadata
    catalog for all ORM models in the application.
    """

    pass


engine = create_async_engine(
    url=DB_URL + DB_NAME,
    pool_size=25,  # persistent connections to keep open in the pool (concurrent database operations)
    max_overflow=10,  # emergency spillover connection, if the pool is full
    pool_recycle=3600,  # Forces connection recycling to prevent server-side drops due to inactive timeout limits
    echo=False,  # print mysql queries to console
)

async_session = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,  # sonst sind Objekte nach commit() "leer" bei Zugriff
)
