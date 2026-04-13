from sqlalchemy import create_engine, Column, BigInteger, String, Text, Enum, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime
from shared.config import settings

DATABASE_URL = (
    f"mysql+pymysql://{settings.mysql_user}:{settings.mysql_password}"
    f"@{settings.mysql_host}:{settings.mysql_port}/{settings.mysql_database}"
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    discord_id = Column(String(32), nullable=False, unique=True)
    discord_username = Column(String(100), nullable=False)
    ecampus_id = Column(String(50), nullable=False)
    ecampus_pw_enc = Column(Text, nullable=False)
    status = Column(Enum("pending", "approved", "rejected"), nullable=False, default="pending")
    agreed_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_session():
    return SessionLocal()
