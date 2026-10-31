from pydantic import BaseModel, Field
from typing import List, Optional

# Modele dla struktury wyjściowej z LLM
class ErrorDetail(BaseModel):
    mistake: str
    correction: str
    explanation: str

class LLMResponse(BaseModel):
    bot_response: str
    errors: List[ErrorDetail] = []

# Modele żądań i odpowiedzi dla API
class MessageRequest(BaseModel):
    session_id: int
    content: str
    native_language: str
    language: str
    level: str
    
class MessageResponse(BaseModel):
    bot_response: str
    wpm: float
    unique_words_count: int
    total_errors: int
    errors_details: List[ErrorDetail]