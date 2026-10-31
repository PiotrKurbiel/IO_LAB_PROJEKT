import re

def calculate_wpm(word_count: int, last_message_timestamp: float, current_timestamp: float) -> float:
    """Oblicza czas pisania wyrażony w słowach na minutę (WPM)."""
    time_diff_minutes = (current_timestamp - last_message_timestamp) / 60.0
    if time_diff_minutes <= 0:
        return float(word_count)
    return round(word_count / time_diff_minutes, 2)

def update_unique_words(current_text: str, existing_unique_words: set) -> set:
    """Aktualizuje zbiór unikalnych słów."""
    words = set(re.findall(r'\b\w+\b', current_text.lower()))
    return existing_unique_words.union(words)

def calculate_error_percentage(total_errors: int, user_text: str) -> float:
    """Oblicza % błędów na zdanie."""
    sentences = max(1, len(re.split(r'[.!?]+', user_text)) - 1)
    return round((total_errors / sentences) * 100, 2)