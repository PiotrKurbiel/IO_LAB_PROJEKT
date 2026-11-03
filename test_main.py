import asyncio
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

from stats_service import calculate_wpm, calculate_error_percentage, count_sentences, count_words, update_unique_words
from llm_service import parse_llm_response, generate_bot_response
from schemas import LLMResponse, ErrorDetail
from models import Base
from database import get_db
from main import app, limiter

# ───────────────────────────────────────────
# Testy jednostkowe – statystyki
# ───────────────────────────────────────────

def test_wpm_calculation():
    # 30 słów wpisane w pół minuty = 60 WPM
    wpm = calculate_wpm(word_count=30, last_message_timestamp=0.0, current_timestamp=30.0)
    assert wpm == 60.0 # Test jednostkowy sprawdzający poprawność wyliczania statystyk[cite: 1]

def test_error_percentage():
    # 2 błędy w 4 zdaniach = 50%
    text = "Hello! How are you? I am fine. And you?"
    perc = calculate_error_percentage(total_errors=2, user_text=text)
    assert perc == 50.0

def test_sentences_without_punctuation():
    # Wiadomość bez kropki na końcu to też zdanie: 1 błąd w 1 zdaniu = 100%
    assert count_sentences("She go yesterday") == 1
    assert count_sentences("Hello! How are you") == 2
    perc = calculate_error_percentage(total_errors=1, user_text="She go yesterday")
    assert perc == 100.0

def test_word_count():
    assert count_words("She go to school yesterday.") == 5
    assert count_words("  Hello   world  ") == 2

def test_unique_words():
    # Wielkość liter i interpunkcja nie tworzą nowych słów
    words = update_unique_words("I like cats. I LIKE dogs!", set())
    assert words == {"i", "like", "cats", "dogs"}
    # Kolejna wiadomość dokłada tylko nowe słowa
    words = update_unique_words("Cats are cute", words)
    assert len(words) == 6

# ───────────────────────────────────────────
# Testy jednostkowe – odczyt odpowiedzi JSON z LLM
# ───────────────────────────────────────────

def test_parse_llm_json():
    text = '```json\n{"bot_response": "Where did she go?", "errors": [{"mistake": "go", "correction": "went", "explanation": "Czas przeszły"}]}\n```'
    result = parse_llm_response(text)
    assert result.bot_response == "Where did she go?"
    assert len(result.errors) == 1
    assert result.errors[0].correction == "went"

def test_parse_llm_json_without_errors():
    result = parse_llm_response('{"bot_response": "Great!", "errors": []}')
    assert result.bot_response == "Great!"
    assert result.errors == []

def test_parse_llm_invalid_json():
    # Odpowiedź nie jest JSON-em – sama odpowiedź bota, bez analizy błędów[cite: 1]
    result = parse_llm_response("Sorry, something went wrong")
    assert result.bot_response == "Sorry, something went wrong"
    assert result.errors == []

def test_parse_llm_json_wrong_format():
    # Poprawny JSON, ale bez wymaganych pól – też bez analizy błędów
    result = parse_llm_response('{"answer": "Hi"}')
    assert result.errors == []

# ───────────────────────────────────────────
# Obsługa błędów API LLM (bez prawdziwych zapytań)[cite: 1]
# ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_llm_timeout_no_retry(mocker):
    # Brak odpowiedzi w 30 s – przerwanie od razu, bez ponawiania
    def timeout(coro, timeout):
        coro.close()
        raise asyncio.TimeoutError
    wait_for = mocker.patch("llm_service.asyncio.wait_for", side_effect=timeout)
    with pytest.raises(Exception, match="Brak odpowiedzi z serwera w ciągu 30 s."):
        await generate_bot_response("Hello", [], "EN", "PL", "B1")
    assert wait_for.call_count == 1

@pytest.mark.asyncio
async def test_llm_retries_then_message(mocker):
    # 429/503 – 3 ponowienia z rosnącym odstępem 1 s, 2 s, 4 s, potem komunikat
    def unavailable(coro, timeout):
        coro.close()
        raise RuntimeError("503 Service Unavailable")
    wait_for = mocker.patch("llm_service.asyncio.wait_for", side_effect=unavailable)
    sleep = mocker.patch("llm_service.asyncio.sleep")
    with pytest.raises(Exception, match="Spróbuj ponownie za chwilę"):
        await generate_bot_response("Hello", [], "EN", "PL", "B1")
    assert wait_for.call_count == 4
    assert [c.args[0] for c in sleep.call_args_list] == [1, 2, 4]

# ───────────────────────────────────────────
# Testy backendu z atrapą LLM[cite: 1]
# ───────────────────────────────────────────

@pytest_asyncio.fixture
async def client():
    # Baza w pamięci (SQLite) zamiast PostgreSQL – testy nie potrzebują Dockera
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    limiter.reset()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
    await engine.dispose()

async def _create_session(client) -> int:
    """Rejestruje użytkownika i zakłada rozmowę EN B2; zwraca session_id."""
    user = (await client.post("/auth/register", json={
        "email": "jan@test.pl", "password": "haslo123", "username": "jan", "native_language": "PL"
    })).json()
    session = (await client.post("/chat/reset", params={
        "user_id": user["user_id"], "language": "EN", "level": "B2"
    })).json()
    return session["session_id"]

def _message(session_id: int, content: str) -> dict:
    return {"session_id": session_id, "content": content, "native_language": "PL", "language": "EN", "level": "B2"}

@pytest.mark.asyncio
async def test_login(client):
    # TC1 – logowanie poprawnym i błędnym hasłem
    await _create_session(client)
    ok = await client.post("/auth/login", json={"email": "jan@test.pl", "password": "haslo123"})
    assert ok.status_code == 200
    bad = await client.post("/auth/login", json={"email": "jan@test.pl", "password": "zle"})
    assert bad.status_code == 401

@pytest.mark.asyncio
async def test_chat_message_with_mock_llm(client, mocker):
    # Atrapa LLM – przygotowana odpowiedź zamiast prawdziwego API Gemini (nie zużywa limitu)
    mocker.patch("main.generate_bot_response", return_value=LLMResponse(
        bot_response="Where did she go?",
        errors=[ErrorDetail(mistake="go", correction="went", explanation="Czas przeszły")]
    ))
    session_id = await _create_session(client)

    resp = await client.post("/chat/message", json=_message(session_id, "She go to school yesterday."))
    assert resp.status_code == 200
    data = resp.json()
    assert data["bot_response"] == "Where did she go?"
    assert data["total_errors"] == 1
    assert data["errors_details"][0]["correction"] == "went"
    assert data["unique_words_count"] == 5

    # Wiadomości zapisane w bazie w poprawnej kolejności (TC7)
    messages = (await client.get(f"/sessions/{session_id}/messages")).json()
    assert [m["sender"] for m in messages] == ["user", "bot"]

    # Statystyki sesji odtworzone z raportu
    stats = (await client.get(f"/sessions/{session_id}/stats")).json()
    assert stats["total_errors"] == 1

@pytest.mark.asyncio
async def test_chat_message_api_failure(client, mocker):
    # Symulacja awarii API LLM – komunikat dla użytkownika i nic nie trafia do bazy[cite: 1]
    mocker.patch("main.generate_bot_response", side_effect=Exception("Spróbuj ponownie za chwilę"))
    session_id = await _create_session(client)

    resp = await client.post("/chat/message", json=_message(session_id, "Hello!"))
    assert resp.status_code == 503
    assert resp.json()["detail"] == "Spróbuj ponownie za chwilę"

    messages = (await client.get(f"/sessions/{session_id}/messages")).json()
    assert messages == []
