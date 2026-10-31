import time
from fastapi import FastAPI, HTTPException, Request
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from schemas import MessageRequest, MessageResponse
from llm_service import generate_bot_response
from stats_service import calculate_wpm, update_unique_words

limiter = Limiter(key_func=get_remote_address)
app = FastAPI()
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# W pamięci operacyjnej do testów bez podpiętej jeszcze bazy danych
# Zastąp to zapytaniami do bazy PostgreSQL (np. używając asyncpg lub SQLAlchemy)
mock_db_history = []
mock_db_unique_words = set()
mock_db_last_timestamp = time.time()

@app.post("/chat/message", response_model=MessageResponse)
@limiter.limit("10/minute") # Limit zapytań w celu ochrony API[cite: 1]
async def send_message(request: Request, msg_req: MessageRequest):
    global mock_db_last_timestamp, mock_db_unique_words
    
    current_time = time.time()
    word_count = len(msg_req.content.split())
    
    try:
        # Komunikacja z API LLM[cite: 1]
        llm_response = await generate_bot_response(
            user_content=msg_req.content,
            history=mock_db_history,
            lang=msg_req.language,
            native_lang=msg_req.native_language,
            level=msg_req.level
        )
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))
        
    # Aktualizacja statystyk[cite: 1]
    mock_db_unique_words = update_unique_words(msg_req.content, mock_db_unique_words)
    wpm = calculate_wpm(word_count, mock_db_last_timestamp, current_time)
    
    # Zapis rozmowy i timestampu (Mock DB)
    mock_db_history.append(f"User: {msg_req.content}")
    mock_db_history.append(f"Bot: {llm_response.bot_response}")
    mock_db_last_timestamp = time.time() # Aktualizowany po każdej wiadomości[cite: 1]
    
    return MessageResponse(
        bot_response=llm_response.bot_response,
        wpm=wpm,
        unique_words_count=len(mock_db_unique_words),
        total_errors=len(llm_response.errors),
        errors_details=llm_response.errors
    )

@app.post("/chat/reset")
async def reset_session():
    """Tworzy nową sesję i zeruje kontekst[cite: 1]."""
    global mock_db_history, mock_db_unique_words, mock_db_last_timestamp
    mock_db_history.clear()
    mock_db_unique_words.clear()
    mock_db_last_timestamp = time.time()
    return {"message": "Sesja zresetowana pomyślnie. Utworzono nowy session_id."}