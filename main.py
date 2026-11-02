import time
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, Request, Depends
from contextlib import asynccontextmanager
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from schemas import MessageRequest, MessageResponse
from llm_service import generate_bot_response
from stats_service import calculate_wpm, update_unique_words
from database import get_db, engine
from models import Base, Session, Message, Report, User

limiter = Limiter(key_func=get_remote_address)

# Automatyczne tworzenie tabel przy starcie aplikacji
@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield

app = FastAPI(lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

@app.post("/chat/message", response_model=MessageResponse)
@limiter.limit("10/minute")
async def send_message(request: Request, msg_req: MessageRequest, db: AsyncSession = Depends(get_db)):
    current_time = time.time()
    word_count = len(msg_req.content.split())
    
    # 1. Sprawdzenie, czy sesja istnieje
    session_result = await db.execute(select(Session).where(Session.session_id == msg_req.session_id))
    db_session = session_result.scalar_one_or_none()
    if not db_session:
        raise HTTPException(status_code=404, detail="Nie znaleziono sesji.")

    # 2. Pobranie historii 4 ostatnich wiadomości (najstarsze pierwsze do kontekstu)
    hist_stmt = select(Message).where(Message.session_id == msg_req.session_id).order_by(Message.timestamp.desc()).limit(4)
    hist_result = await db.execute(hist_stmt)
    db_messages = hist_result.scalars().all()[::-1]
    
    history = [f"User: {m.content}" if m.sender == 'user' else f"Bot: {m.content}" for m in db_messages]

    # 3. Pobranie wszystkich wiadomości z sesji, by policzyć unikalne słowa
    all_msgs_stmt = select(Message.content).where(Message.session_id == msg_req.session_id)
    all_msgs_result = await db.execute(all_msgs_stmt)
    db_unique_words = set()
    for content in all_msgs_result.scalars():
        db_unique_words = update_unique_words(content, db_unique_words)
    db_unique_words = update_unique_words(msg_req.content, db_unique_words) # Aktualna wiadomość

    try:
        llm_response = await generate_bot_response(
            user_content=msg_req.content,
            history=history,
            lang=msg_req.language,
            native_lang=msg_req.native_language,
            level=msg_req.level
        )
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))

    # 4. Wyliczenie WPM na podstawie ostatniej wiadomości użytkownika
    last_user_msg_stmt = select(Message.timestamp).where(Message.session_id == msg_req.session_id, Message.sender == 'user').order_by(Message.timestamp.desc()).limit(1)
    last_msg_result = await db.execute(last_user_msg_stmt)
    last_timestamp_dt = last_msg_result.scalar_one_or_none()
    
    last_timestamp = last_timestamp_dt.timestamp() if last_timestamp_dt else current_time - 10 # Zabezpieczenie pierwszej wiadomości
    wpm = calculate_wpm(word_count, last_timestamp, current_time)

    # 5. Zapis logów konwersacji (Wiadomości) do bazy
    new_user_msg = Message(session_id=msg_req.session_id, sender='user', content=msg_req.content, word_count=word_count)
    new_bot_msg = Message(session_id=msg_req.session_id, sender='bot', content=llm_response.bot_response, word_count=len(llm_response.bot_response.split()))
    
    # 6. Zapis raportu błędu
    new_report = Report(
        session_id=msg_req.session_id,
        wpm=wpm,
        unique_words_count=len(db_unique_words),
        total_errors=len(llm_response.errors),
        errors_details=[err.dict() for err in llm_response.errors]
    )

    db.add_all([new_user_msg, new_bot_msg, new_report])
    await db.commit()

    return MessageResponse(
        bot_response=llm_response.bot_response,
        wpm=wpm,
        unique_words_count=len(db_unique_words),
        total_errors=len(llm_response.errors),
        errors_details=llm_response.errors
    )

@app.post("/chat/reset")
async def reset_session(user_id: int, language: str, level: str, db: AsyncSession = Depends(get_db)):
    """Tworzy nowy wpis w tabeli Sessions przypisany do Użytkownika."""
    new_session = Session(user_id=user_id, language=language, level=level)
    db.add(new_session)
    await db.commit()
    await db.refresh(new_session)
    return {"message": "Utworzono nową sesję.", "session_id": new_session.session_id}