import asyncio
import json
import os
import google.generativeai as genai
from dotenv import load_dotenv
from pydantic import ValidationError
from schemas import LLMResponse

# Klucz API wczytywany z pliku .env (GOOGLE_API_KEY=...) lub ze zmiennej środowiskowej
load_dotenv()
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

# Przy przeciążeniu (503) kolejna próba idzie do następnego modelu z listy
MODEL_NAMES = [os.getenv("GEMINI_MODEL", "gemini-3.5-flash"), "gemini-3.6-flash", "gemini-3-flash-preview"]
models = [
    genai.GenerativeModel(name, generation_config={"response_mime_type": "application/json"})
    for name in MODEL_NAMES
]

def parse_llm_response(text: str) -> LLMResponse:
    """Odczytuje odpowiedź LLM (JSON) do struktury bot_response + errors."""
    # Oczyszczenie odpowiedzi z markdowna (częsty problem w LLM)
    raw_json = text.replace("```json", "").replace("```", "").strip()
    try:
        data = json.loads(raw_json)
        return LLMResponse(**data)
    except (json.JSONDecodeError, TypeError, ValidationError):
        # Zabezpieczenie: Odpowiedź nie jest poprawnym JSON-em[cite: 1]
        # Zwraca samą odpowiedź tekstową bez analizy błędów[cite: 1]
        return LLMResponse(bot_response=text, errors=[])

async def generate_bot_response(user_content: str, history: list, lang: str, native_lang: str, level: str) -> LLMResponse:
    # Prompt Systemowy[cite: 1]
    system_prompt = (
        f"Jesteś konwersacyjnym nauczycielem języka docelowego: {lang}. "
        f"Językiem ojczystym użytkownika jest: {native_lang}. "
        f"Dostosuj trudność swoich odpowiedzi rygorystycznie do poziomu {level}. "
        f"Zwróć wynik wyłącznie jako obiekt JSON w formacie: "
        f'{{"bot_response": "twoja odpowiedź w języku {lang}", '
        f'"errors": [{{"mistake": "błędny fragment", "correction": "poprawna forma", '
        f'"explanation": "wyjaśnienie w języku {native_lang}"}}]}}. '
        f"Każdy błąd w wiadomości użytkownika to osobny element listy errors; jeśli błędów nie ma, zwróć pustą listę."
    )
    
    # Ograniczenie historii rozmowy do 3-4 ostatnich wiadomości[cite: 1]
    prompt = f"{system_prompt}\nHistoria: {history[-4:]}\nWiadomość użytkownika: {user_content}"
    
    delays = [1, 2, 4]
    
    for attempt in range(4):
        try:
            # Przerywanie zapytania w przypadku braku odpowiedzi w ciągu 30s[cite: 1]
            # retry=None – bez wewnętrznych ponowień biblioteki, ponawiamy sami (z innym modelem);
            # timeout biblioteki dłuższy niż 30 s, żeby to wait_for decydował o przerwaniu
            model = models[attempt % len(models)]
            response = await asyncio.wait_for(
                asyncio.to_thread(model.generate_content, prompt, request_options={"retry": None, "timeout": 35}),
                timeout=30.0
            )
            return parse_llm_response(response.text)

        except asyncio.TimeoutError:
            # Brak odpowiedzi w 30 s – przerywamy od razu, bez ponawiania[cite: 1]
            raise Exception("Brak odpowiedzi z serwera w ciągu 30 s.")
        except Exception as e:
            # Sytuacja: Przekroczony limit zapytań (429) lub niedostępność (503)[cite: 1]
            if attempt == 3:
                raise Exception("Spróbuj ponownie za chwilę") #[cite: 1]
            await asyncio.sleep(delays[attempt]) # Rosnący odstęp: 1s, 2s, 4s[cite: 1]