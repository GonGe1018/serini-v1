"""create users table

Revision ID: 0001
Revises:
Create Date: 2026-04-13

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("discord_id", sa.String(32), nullable=False, unique=True),
        sa.Column("discord_username", sa.String(100), nullable=False),
        sa.Column("ecampus_id", sa.String(50), nullable=False),
        sa.Column("ecampus_pw_enc", sa.Text, nullable=False),
        sa.Column("status", sa.Enum("pending", "approved", "rejected"), nullable=False, server_default="pending"),
        sa.Column("agreed_at", sa.DateTime, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("users")
