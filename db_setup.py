"""Sprawdza bazę danych przed startem aplikacji – uruchamiany przez uruchom.bat.

Jeśli na komputerze działa już własny PostgreSQL z innym hasłem niż domyślne,
pyta o dane logowania, zakłada w nim bazę projekt_lab i zapisuje połączenie w .env.
Jeśli żadnej bazy nie ma, uruchom.bat stawia ją w Dockerze.

Kody wyjścia: 0 – baza gotowa, 10 – brak bazy (trzeba Dockera), 1 – przerwano.
"""
import asyncio
import getpass
import sys
from pathlib import Path

import asyncpg
from dotenv import dotenv_values, set_key
from sqlalchemy.engine import URL, make_url

from database import DEFAULT_DATABASE_URL

ENV_FILE = Path(__file__).with_name(".env")
READY, NEED_DOCKER, ABORTED = 0, 10, 1


def build_database_url(user: str, password: str, host: str = "localhost", port: int = 5432,
                       database: str = "projekt_lab") -> str:
    """Adres bazy dla SQLAlchemy – hasło ze znakami specjalnymi jest poprawnie zakodowane."""
    return URL.create("postgresql+asyncpg", username=user, password=password,
                      host=host, port=port, database=database).render_as_string(hide_password=False)


async def _connect(url: str, database: str | None = None):
    u = make_url(url)
    return await asyncpg.connect(user=u.username, password=u.password, host=u.host,
                                 port=u.port or 5432, database=database or u.database, timeout=5)


async def check_database(url: str) -> str:
    """Zwraca 'ok', 'no_database' (brak bazy projekt_lab), 'bad_login' albo 'no_server'."""
    try:
        conn = await _connect(url)
    except asyncpg.InvalidCatalogNameError:
        return "no_database"
    except (asyncpg.InvalidPasswordError, asyncpg.InvalidAuthorizationSpecificationError):
        return "bad_login"
    except (OSError, asyncio.TimeoutError):
        return "no_server"
    await conn.close()
    return "ok"


async def create_database(url: str) -> None:
    """Zakłada bazę projekt_lab na serwerze (łączy się przez systemową bazę 'postgres')."""
    conn = await _connect(url, database="postgres")
    try:
        await conn.execute(f'CREATE DATABASE "{make_url(url).database}"')
    finally:
        await conn.close()


def ensure_database(url: str) -> str:
    """Sprawdza bazę i w razie potrzeby ją zakłada; zwraca status jak check_database."""
    status = asyncio.run(check_database(url))
    if status == "no_database":
        asyncio.run(create_database(url))
        print(f"Utworzono bazę {make_url(url).database}.")
        status = "ok"
    return status


def read_password(prompt: str) -> str:
    # getpass ukrywa wpisywane znaki; bez konsoli (np. w testach) czyta zwykle ze standardowego wejścia
    return getpass.getpass(prompt) if sys.stdin.isatty() else input(prompt)


def ask_own_database() -> str | None:
    """Pyta o dane logowania do własnego PostgreSQL; zwraca działający adres albo None."""
    print("Na tym komputerze działa już PostgreSQL (port 5432) z innym hasłem niż domyślne.")
    print("Aplikacja może korzystać z tej bazy - podaj dane logowania (puste hasło = przerwij).")
    for _ in range(3):
        try:
            user = input("Użytkownik [postgres]: ").strip() or "postgres"
            password = read_password("Hasło: ")
        except (EOFError, KeyboardInterrupt):
            return None
        if not password:
            return None
        url = build_database_url(user, password)
        if ensure_database(url) == "ok":
            return url
        print("Nie udało się zalogować - spróbuj jeszcze raz.")
    return None


def main() -> int:
    # Polskie znaki także wtedy, gdy wejście/wyjście nie jest zwykłą konsolą (uruchom.bat ustawia chcp 65001)
    for stream in (sys.stdin, sys.stdout):
        stream.reconfigure(encoding="utf-8", errors="replace")

    saved_url = dotenv_values(ENV_FILE).get("DATABASE_URL")
    status = ensure_database(saved_url or DEFAULT_DATABASE_URL)

    if status == "ok":
        return READY
    if status == "no_server" and not saved_url:
        return NEED_DOCKER
    if status == "no_server":
        print("Baza zapisana w .env (DATABASE_URL) nie odpowiada - włącz swój PostgreSQL")
        print("albo usuń linię DATABASE_URL z pliku .env, żeby użyć bazy w Dockerze.")
        return ABORTED

    if saved_url:
        print("Dane logowania do bazy zapisane w .env przestały działać.")
    own_url = ask_own_database()
    if not own_url:
        print("Przerwano. Możesz też zatrzymać swój PostgreSQL (services.msc -> postgresql)")
        print("- wtedy aplikacja sama postawi bazę w Dockerze.")
        return ABORTED
    ENV_FILE.touch()
    set_key(ENV_FILE, "DATABASE_URL", own_url)
    print("Połączono z Twoją bazą. Dane zapisane w .env - następnym razem nie trzeba ich podawać.")
    return READY


if __name__ == "__main__":
    sys.exit(main())
