import os
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

# Domyślnie baza z Dockera (uruchom.bat); własną bazę zapisuje w .env jako DATABASE_URL skrypt db_setup.py
DEFAULT_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/projekt_lab"

load_dotenv()
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)

engine = create_async_engine(SQLALCHEMY_DATABASE_URL, echo=True)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    expire_on_commit=False
)

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
