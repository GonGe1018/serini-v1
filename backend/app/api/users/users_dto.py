from pydantic import BaseModel
from typing import Literal
from datetime import datetime


class UserResponseDTO(BaseModel):
    id: int
    discord_id: str
    discord_username: str
    ecampus_id: str
    status: Literal["pending", "approved", "rejected"]
    agreed_at: datetime
    created_at: datetime

    class Config:
        from_attributes = True


class StatusUpdateDTO(BaseModel):
    status: Literal["approved", "rejected"]


class TokenResponseDTO(BaseModel):
    access_token: str
    token_type: str = "bearer"
