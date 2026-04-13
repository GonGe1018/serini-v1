from sqlalchemy import Column, BigInteger, String, Text, Enum, DateTime
from datetime import datetime

from app.db.database import Base


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
