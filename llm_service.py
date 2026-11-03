import asyncio
import json
import os
import google.generativeai as genai
from dotenv import load_dotenv
from schemas import LLMResponse

# Klucz API wczytywany z pliku .env (GOOGLE_API_KEY=...) lub ze zmiennej środowiskowej
load_dotenv()
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
model = genai.GenerativeModel(os.getenv("GEMINI_MODEL", "gemini-2.5-flash"))

async def generate_bot_response(user_content: str, history: list, lang: str, native_lang: str, level: str) -> LLMResponse:
    # Prompt Systemowy[cite: 1]
    system_prompt = (
        f"Jesteś konwersacyjnym nauczycielem języka docelowego: {lang}. "
        f"Językiem ojczystym użytkownika jest: {native_lang}. "
        f"Dostosuj trudność swoich odpowiedzi rygorystycznie do poziomu {level}. "
        f"Zwróć wynik jako obiekt JSON: bot_response w języku {lang}, "
        f"a każde wyjaśnienie pomyłki w polu explanation w języku {native_lang}."
    )
    
    # Ograniczenie historii rozmowy do 3-4 ostatnich wiadomości[cite: 1]
    prompt = f"{system_prompt}\nHistoria: {history[-4:]}\nWiadomość użytkownika: {user_content}"
    
    delays = [1, 2, 4]
    
    for attempt in range(4):
        try:
            # Przerywanie zapytania w przypadku braku odpowiedzi w ciągu 30s[cite: 1]
            response = await asyncio.wait_for(
                asyncio.to_thread(model.generate_content, prompt), 
                timeout=30.0
            )
            
            # Próba parsowania JSON
            try:
                # Oczyszczenie odpowiedzi z markdowna (częsty problem w LLM)
                raw_json = response.text.replace("```json", "").replace("```", "").strip()
                data = json.loads(raw_json)
                return LLMResponse(**data)
            except (json.JSONDecodeError, TypeError):
                # Zabezpieczenie: Odpowiedź nie jest poprawnym JSON-em[cite: 1]
                # Zwraca samą odpowiedź tekstową bez analizy błędów[cite: 1]
                return LLMResponse(bot_response=response.text, errors=[])
                
        except asyncio.TimeoutError:
            if attempt == 3:
                raise Exception("Brak odpowiedzi z serwera w ciągu 30 s.") #[cite: 1]
        except Exception as e:
            # Sytuacja: Przekroczony limit zapytań (429) lub niedostępność (503)[cite: 1]
            if attempt == 3:
                raise Exception("Spróbuj ponownie za chwilę") #[cite: 1]
            await asyncio.sleep(delays[attempt]) # Rosnący odstęp: 1s, 2s, 4s[cite: 1]