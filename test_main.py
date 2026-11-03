import pytest
from stats_service import calculate_wpm, calculate_error_percentage, count_sentences

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

@pytest.mark.asyncio
async def test_mock_llm_response(mocker):
    # Testy z atrapą LLM symulującą przygotowaną odpowiedź by nie zużywać limitu API[cite: 1]
    mock_response = {
        "bot_response": "I went to school yesterday.",
        "errors": [{"mistake": "go", "correction": "went", "explanation": "Czas przeszły"}]
    }
    
    # Mockujemy funkcję komunikującą się z Gemini
    mocker.patch("llm_service.generate_bot_response", return_value=mock_response)
    
    # Tutaj można wstrzyknąć klienta testowego FastAPI i sprawdzić odpowiedź endpointa