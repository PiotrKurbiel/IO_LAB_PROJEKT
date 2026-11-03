import streamlit as st
import requests
from stats_service import calculate_error_percentage

# ───────────────────────────────────────────
# Konfiguracja
# ───────────────────────────────────────────
API_URL = "http://localhost:8000"

LANGUAGES = {"Polski": "PL", "Angielski": "EN", "Hiszpański": "ES"}
LEVELS = ["A1", "A2", "B1", "B2", "C1", "C2"]

st.set_page_config(
    page_title="LangChat – nauka języków",
    page_icon="💬",
    layout="wide"
)

# ───────────────────────────────────────────
# Pomocnicze funkcje API
# ───────────────────────────────────────────

def api_register(email: str, password: str, username: str, native_language: str):
    try:
        r = requests.post(f"{API_URL}/auth/register", json={
            "email": email, "password": password,
            "username": username, "native_language": native_language
        }, timeout=10)
        return r
    except requests.exceptions.ConnectionError:
        return None

def api_login(email: str, password: str):
    try:
        r = requests.post(f"{API_URL}/auth/login", json={"email": email, "password": password}, timeout=10)
        return r
    except requests.exceptions.ConnectionError:
        return None

def api_get_sessions(user_id: int):
    try:
        r = requests.get(f"{API_URL}/sessions/{user_id}", timeout=10)
        if r.status_code == 200:
            return r.json()
    except requests.exceptions.ConnectionError:
        pass
    return []

def api_get_messages(session_id: int):
    try:
        r = requests.get(f"{API_URL}/sessions/{session_id}/messages", timeout=10)
        if r.status_code == 200:
            return r.json()
    except requests.exceptions.ConnectionError:
        pass
    return []

def api_reset_session(user_id: int, language: str, level: str):
    try:
        r = requests.post(f"{API_URL}/chat/reset", params={
            "user_id": user_id, "language": language, "level": level
        }, timeout=10)
        if r.status_code == 200:
            return r.json()
    except requests.exceptions.ConnectionError:
        pass
    return None

def api_send_message(session_id: int, content: str, language: str, level: str, native_language: str):
    try:
        r = requests.post(f"{API_URL}/chat/message", json={
            "session_id": session_id,
            "content": content,
            "language": language,
            "level": level,
            "native_language": native_language
        }, timeout=35)
        return r
    except requests.exceptions.ConnectionError:
        return None

# ───────────────────────────────────────────
# Stan sesji Streamlit
# ───────────────────────────────────────────

def init_state():
    defaults = {
        "logged_in": False,
        "user": None,            # dict: user_id, username, native_language, email
        "session_id": None,
        "language_code": "EN",
        "level": "B1",
        "messages": [],          # lista dict: {sender, content}
        "last_errors": [],       # błędy z ostatniej wiadomości
        "stats": {               # statystyki bieżącej sesji
            "wpm": 0.0,
            "unique_words_count": 0,
            "total_errors": 0,
            "total_words": 0,
            "sentence_count": 0,
        },
        "show_register": False,
        "api_error": None,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val

init_state()

# ───────────────────────────────────────────
# Ekran logowania / rejestracji
# ───────────────────────────────────────────

def render_login():
    st.title("💬 LangChat")
    st.subheader("Konwersacyjny asystent nauki języków")

    if st.session_state.api_error:
        st.error(st.session_state.api_error)
        st.session_state.api_error = None

    tab_login, tab_register = st.tabs(["Zaloguj się", "Zarejestruj się"])

    with tab_login:
        with st.form("login_form"):
            email = st.text_input("Adres e-mail", placeholder="np. jan@example.com")
            password = st.text_input("Hasło", type="password")
            submitted = st.form_submit_button("Zaloguj", use_container_width=True)

        if submitted:
            if not email or not password:
                st.warning("Wypełnij wszystkie pola.")
            else:
                with st.spinner("Logowanie…"):
                    resp = api_login(email, password)
                if resp is None:
                    st.error("Nie można połączyć się z serwerem. Sprawdź, czy backend działa.")
                elif resp.status_code == 200:
                    st.session_state.user = resp.json()
                    st.session_state.logged_in = True
                    st.rerun()
                else:
                    st.error(resp.json().get("detail", "Błąd logowania."))

    with tab_register:
        with st.form("register_form"):
            reg_username = st.text_input("Nazwa użytkownika")
            reg_email = st.text_input("Adres e-mail", key="reg_email")
            reg_password = st.text_input("Hasło", type="password", key="reg_pass")
            reg_native = st.selectbox(
                "Twój język ojczysty",
                options=list(LANGUAGES.keys()),
                key="reg_native"
            )
            reg_submitted = st.form_submit_button("Zarejestruj się", use_container_width=True)

        if reg_submitted:
            if not all([reg_username, reg_email, reg_password]):
                st.warning("Wypełnij wszystkie pola.")
            else:
                native_code = LANGUAGES[reg_native]
                with st.spinner("Rejestracja…"):
                    resp = api_register(reg_email, reg_password, reg_username, native_code)
                if resp is None:
                    st.error("Nie można połączyć się z serwerem.")
                elif resp.status_code == 200:
                    st.success("Konto utworzone! Możesz się teraz zalogować.")
                elif resp.status_code == 409:
                    st.error("Konto z tym adresem e-mail już istnieje.")
                else:
                    st.error(resp.json().get("detail", "Błąd rejestracji."))


# ───────────────────────────────────────────
# Główny interfejs (po zalogowaniu)
# ───────────────────────────────────────────

def render_app():
    user = st.session_state.user

    # ── Panel boczny ──────────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown(f"### 👤 {user['username']}")
        st.caption(user['email'])
        st.divider()

        st.subheader("⚙️ Ustawienia sesji")
        lang_label = st.selectbox("Język nauki", options=list(LANGUAGES.keys()))
        selected_lang = LANGUAGES[lang_label]
        selected_level = st.selectbox("Poziom zaawansowania", options=LEVELS, index=LEVELS.index("B1"))

        if st.button("▶ Nowa rozmowa", use_container_width=True):
            _start_new_session(user["user_id"], selected_lang, selected_level)

        st.divider()

        # Historia sesji
        st.subheader("📂 Historia rozmów")
        sessions = api_get_sessions(user["user_id"])
        if sessions:
            for s in sessions:
                label = f"#{s['session_id']}  {s['language']} · {s['level']}"
                if st.button(label, key=f"sess_{s['session_id']}", use_container_width=True):
                    _load_session(s["session_id"], s["language"], s["level"])
        else:
            st.caption("Brak poprzednich rozmów.")

        st.divider()
        if st.button("🚪 Wyloguj", use_container_width=True):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()

    # ── Główna część ─────────────────────────────────────────────────────────
    if st.session_state.session_id is None:
        st.info("👈 Wybierz ustawienia i kliknij **Nowa rozmowa** lub wczytaj poprzednią rozmowę z panelu bocznego.")
        return

    chat_col, errors_col = st.columns([3, 2])

    # ── Kolumna CHAT ─────────────────────────────────────────────────────────
    with chat_col:
        lang_display = {v: k for k, v in LANGUAGES.items()}.get(st.session_state.language_code, st.session_state.language_code)
        st.subheader(f"💬 CHAT — {lang_display} · {st.session_state.level}")

        # Okno wiadomości
        chat_container = st.container(height=420)
        with chat_container:
            for msg in st.session_state.messages:
                with st.chat_message(msg["sender"] if msg["sender"] == "user" else "assistant"):
                    st.markdown(msg["content"])

        # Pole wpisywania
        user_input = st.chat_input("Wpisz wiadomość…")
        if user_input:
            _handle_send(user_input)

        # Przycisk RESET
        st.divider()
        if st.button("🔄 RESET — nowa rozmowa w tym samym języku", use_container_width=True):
            _start_new_session(
                user["user_id"],
                st.session_state.language_code,
                st.session_state.level
            )

    # ── Kolumna BŁĘDY I POPRAWA ────────────────────────────────────────────
    with errors_col:
        st.subheader("🔴 BŁĘDY I POPRAWA")
        errors = st.session_state.last_errors
        if not errors:
            st.success("Brak błędów w ostatniej wiadomości ✓")
        else:
            for i, err in enumerate(errors, 1):
                with st.expander(f"Błąd {i}: *{err['mistake']}* → **{err['correction']}**", expanded=True):
                    st.markdown(f"💡 {err['explanation']}")

        # ── STATYSTYKI ────────────────────────────────────────────────────
        st.divider()
        st.subheader("📊 STATYSTYKI")
        stats = st.session_state.stats

        c1, c2 = st.columns(2)
        c1.metric("📝 Słów / min (WPM)", f"{stats['wpm']:.1f}")
        c2.metric("📚 Unikalne słowa", stats["unique_words_count"])

        c3, c4 = st.columns(2)
        c3.metric("✍️ Słów łącznie", stats["total_words"])
        error_pct = (
            round((stats["total_errors"] / max(1, stats["sentence_count"])) * 100, 1)
            if stats["sentence_count"] > 0 else 0.0
        )
        c4.metric("❌ % błędów / zdanie", f"{error_pct:.1f}%")


# ───────────────────────────────────────────
# Akcje pomocnicze
# ───────────────────────────────────────────

def _start_new_session(user_id: int, language: str, level: str):
    """Tworzy nową sesję i zeruje stan czatu."""
    with st.spinner("Tworzenie nowej sesji…"):
        result = api_reset_session(user_id, language, level)
    if result is None:
        st.error("Nie można połączyć się z serwerem.")
        return
    st.session_state.session_id = result["session_id"]
    st.session_state.language_code = language
    st.session_state.level = level
    st.session_state.messages = []
    st.session_state.last_errors = []
    st.session_state.stats = {
        "wpm": 0.0, "unique_words_count": 0,
        "total_errors": 0, "total_words": 0, "sentence_count": 0
    }
    st.rerun()


def _load_session(session_id: int, language: str, level: str):
    """Wczytuje historię wiadomości z istniejącej sesji."""
    with st.spinner("Wczytywanie rozmowy…"):
        raw_msgs = api_get_messages(session_id)
    st.session_state.session_id = session_id
    st.session_state.language_code = language
    st.session_state.level = level
    st.session_state.messages = [
        {"sender": m["sender"], "content": m["content"]} for m in raw_msgs
    ]
    st.session_state.last_errors = []
    st.session_state.stats = {
        "wpm": 0.0, "unique_words_count": 0,
        "total_errors": 0, "total_words": 0, "sentence_count": 0
    }
    st.rerun()


def _handle_send(content: str):
    """Wysyła wiadomość do backendu i aktualizuje stan."""
    import re

    # Optymistyczne dodanie wiadomości użytkownika do czatu
    st.session_state.messages.append({"sender": "user", "content": content})

    user = st.session_state.user
    with st.spinner("Bot pisze…"):
        resp = api_send_message(
            session_id=st.session_state.session_id,
            content=content,
            language=st.session_state.language_code,
            level=st.session_state.level,
            native_language=user["native_language"]
        )

    if resp is None:
        st.error("Brak połączenia z serwerem. Spróbuj ponownie.")
        st.session_state.messages.pop()  # Cofnij optymistyczne dodanie
        return

    if resp.status_code == 429:
        st.warning("Przekroczono limit 10 wiadomości na minutę. Poczekaj chwilę.")
        st.session_state.messages.pop()
        return

    if resp.status_code != 200:
        detail = resp.json().get("detail", "Błąd serwera.")
        st.error(f"Błąd: {detail}")
        st.session_state.messages.pop()
        return

    data = resp.json()

    # Dodaj odpowiedź bota
    st.session_state.messages.append({"sender": "bot", "content": data["bot_response"]})

    # Błędy
    st.session_state.last_errors = data.get("errors_details", [])

    # Aktualizuj statystyki
    stats = st.session_state.stats
    stats["wpm"] = data["wpm"]
    stats["unique_words_count"] = data["unique_words_count"]
    stats["total_errors"] += data["total_errors"]
    stats["total_words"] += len(content.split())
    # Liczba zdań z całości wiadomości użytkownika
    all_user_text = " ".join(
        m["content"] for m in st.session_state.messages if m["sender"] == "user"
    )
    stats["sentence_count"] = max(1, len(re.split(r'[.!?]+', all_user_text)) - 1)

    st.rerun()


# ───────────────────────────────────────────
# Routing
# ───────────────────────────────────────────

if st.session_state.logged_in:
    render_app()
else:
    render_login()
