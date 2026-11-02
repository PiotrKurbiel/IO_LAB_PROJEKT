from sqlalchemy import Column, Integer, String, Text, Float, ForeignKey, DateTime
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime, timezone

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'

    user_id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    username = Column(String, nullable=False)
    native_language = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_login = Column(DateTime(timezone=True), nullable=True)

    # Relacja do tabeli Sesje
    sessions = relationship("Session", back_populates="user")

class Session(Base):
    __tablename__ = 'sessions'

    session_id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.user_id'), nullable=False)
    language = Column(String, nullable=False)
    level = Column(String, nullable=False)

    # Relacje
    user = relationship("User", back_populates="sessions")
    messages = relationship("Message", back_populates="session")
    reports = relationship("Report", back_populates="session")

class Message(Base):
    __tablename__ = 'messages'

    msg_id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey('sessions.session_id'), nullable=False)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    sender = Column(String, nullable=False) # 'user' lub 'bot'
    content = Column(Text, nullable=False)
    word_count = Column(Integer, nullable=False)

    # Relacja
    session = relationship("Session", back_populates="messages")

class Report(Base):
    __tablename__ = 'reports'

    report_id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey('sessions.session_id'), nullable=False)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    wpm = Column(Float, nullable=False)
    unique_words_count = Column(Integer, nullable=False)
    total_errors = Column(Integer, nullable=False)
    errors_details = Column(JSONB, nullable=False)

    # Relacja
    session = relationship("Session", back_populates="reports")