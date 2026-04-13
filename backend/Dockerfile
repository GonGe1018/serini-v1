FROM python:3.12-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY backend/pyproject.toml ./
RUN uv pip compile pyproject.toml -o requirements.txt && \
    uv pip install --system -r requirements.txt && \
    rm requirements.txt

COPY backend/ .

RUN useradd -r -s /bin/false appuser
USER appuser

CMD ["python", "-m", "app.main"]
