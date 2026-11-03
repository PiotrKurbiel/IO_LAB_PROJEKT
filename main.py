import time
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, Request, Depends
from contextlib import asynccontextmanager
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import List, Optional

from schemas import MessageRequest, MessageResponse, ErrorDetail
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


# ───────────────────────────────────────────
# Schematy dla endpointów auth
# ───────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: str
    password: str
    username: str
    native_language: str  # np. 'PL', 'EN', 'ES'

class LoginRequest(BaseModel):
    email: str
    password: str

class UserResponse(BaseModel):
    user_id: int
    email: str
    username: str
    native_language: str

class SessionInfo(BaseModel):
    session_id: int
    language: str
    level: str

class MessageInfo(BaseModel):
    msg_id: int
    sender: str
    content: str
    timestamp: str

class SessionStats(BaseModel):
    wpm: float
    unique_words_count: int
    total_errors: int
    last_errors: List[ErrorDetail]


# ───────────────────────────────────────────
# Rejestracja
# ───────────────────────────────────────────

@app.post("/auth/register", response_model=UserResponse)
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """Tworzy nowe konto użytkownika."""
    # Sprawdź unikalność e-mail
    result = await db.execute(select(User).where(User.email == req.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Konto z tym adresem e-mail już istnieje.")

    new_user = User(
        email=req.email,
        username=req.username,
        native_language=req.native_language,
        password_hash=""  # zostanie nadpisany przez set_password
    )
    new_user.set_password(req.password)
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    return UserResponse(
        user_id=new_user.user_id,
        email=new_user.email,
        username=new_user.username,
        native_language=new_user.native_language
    )


# ───────────────────────────────────────────
# Logowanie
# ───────────────────────────────────────────

@app.post("/auth/login", response_model=UserResponse)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Weryfikuje dane logowania i zwraca dane użytkownika."""
    result = await db.execute(select(User).where(User.email == req.email))
    user = result.scalar_one_or_none()

    if not user or not user.verify_password(req.password):
        raise HTTPException(status_code=401, detail="Nieprawidłowy e-mail lub hasło.")

    # Aktualizacja last_login
    user.last_login = datetime.now(timezone.utc)
    await db.commit()

    return UserResponse(
        user_id=user.user_id,
        email=user.email,
        username=user.username,
        native_language=user.native_language
    )


# ───────────────────────────────────────────
# Historia sesji użytkownika
# ───────────────────────────────────────────

@app.get("/sessions/{user_id}", response_model=List[SessionInfo])
async def get_sessions(user_id: int, db: AsyncSession = Depends(get_db)):
    """Zwraca listę wszystkich sesji danego użytkownika (historia rozmów)."""
    result = await db.execute(
        select(Session).where(Session.user_id == user_id).order_by(Session.session_id.desc())
    )
    sessions = result.scalars().all()
    return [SessionInfo(session_id=s.session_id, language=s.language, level=s.level) for s in sessions]


# ───────────────────────────────────────────
# Wiadomości z konkretnej sesji
# ───────────────────────────────────────────

@app.get("/sessions/{session_id}/messages", response_model=List[MessageInfo])
async def get_messages(session_id: int, db: AsyncSession = Depends(get_db)):
    """Zwraca historię wiadomości z podanej sesji w kolejności chronologicznej."""
    result = await db.execute(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.timestamp.asc())
    )
    messages = result.scalars().all()
    return [
        MessageInfo(
            msg_id=m.msg_id,
            sender=m.sender,
            content=m.content,
            timestamp=m.timestamp.isoformat()
        )
        for m in messages
    ]


# ───────────────────────────────────────────
# Statystyki z konkretnej sesji
# ───────────────────────────────────────────

@app.get("/sessions/{session_id}/stats", response_model=SessionStats)
async def get_session_stats(session_id: int, db: AsyncSession = Depends(get_db)):
    """Odtwarza statystyki sesji z zapisanych raportów (np. po wczytaniu starej rozmowy)."""
    result = await db.execute(
        select(Report).where(Report.session_id == session_id).order_by(Report.report_id.asc())
    )
    reports = result.scalars().all()
    if not reports:
        return SessionStats(wpm=0.0, unique_words_count=0, total_errors=0, last_errors=[])

    last = reports[-1]
    return SessionStats(
        wpm=last.wpm,
        unique_words_count=last.unique_words_count,
        total_errors=sum(r.total_errors for r in reports),
        last_errors=last.errors_details
    )


# ───────────────────────────────────────────
# Wysyłanie wiadomości (chat)
# ───────────────────────────────────────────

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

    # 3. Pobranie wszystkich wiadomości użytkownika z sesji, by policzyć jego unikalne słowa
    all_msgs_stmt = select(Message.content).where(
        Message.session_id == msg_req.session_id,
        Message.sender == 'user'
    )
    all_msgs_result = await db.execute(all_msgs_stmt)
    db_unique_words = set()
    for content in all_msgs_result.scalars():
        db_unique_words = update_unique_words(content, db_unique_words)
    db_unique_words = update_unique_words(msg_req.content, db_unique_words)  # Aktualna wiadomość

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
    last_user_msg_stmt = select(Message.timestamp).where(
        Message.session_id == msg_req.session_id,
        Message.sender == 'user'
    ).order_by(Message.timestamp.desc()).limit(1)
    last_msg_result = await db.execute(last_user_msg_stmt)
    last_timestamp_dt = last_msg_result.scalar_one_or_none()

    last_timestamp = last_timestamp_dt.timestamp() if last_timestamp_dt else current_time - 10  # Zabezpieczenie pierwszej wiadomości
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


# ───────────────────────────────────────────
# Reset / Nowa sesja
# ───────────────────────────────────────────

@app.post("/chat/reset", response_model=SessionInfo)
async def reset_session(user_id: int, language: str, level: str, db: AsyncSession = Depends(get_db)):
    """Tworzy nowy wpis w tabeli Sessions przypisany do Użytkownika."""
    new_session = Session(user_id=user_id, language=language, level=level)
    db.add(new_session)
    await db.commit()
    await db.refresh(new_session)
    return SessionInfo(session_id=new_session.session_id, language=new_session.language, level=new_session.level)
