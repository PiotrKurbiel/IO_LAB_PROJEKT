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

def count_sentences(text: str) -> int:
    """Liczy zdania – fragment bez kropki, ! lub ? na końcu też jest zdaniem."""
    return len([s for s in re.split(r'[.!?]+', text) if s.strip()])

def calculate_error_percentage(total_errors: int, user_text: str) -> float:
    """Oblicza % błędów na zdanie."""
    sentences = max(1, count_sentences(user_text))
    return round((total_errors / sentences) * 100, 2)