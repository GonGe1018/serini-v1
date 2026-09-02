FROM python:3.12-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY shared/ /app/shared/
COPY backend/pyproject.toml ./
RUN uv pip install --system /app/shared/ && \
    uv pip compile pyproject.toml -o requirements.txt && \
    uv pip install --system -r requirements.txt && \
    rm requirements.txt

COPY backend/ .

ENV PYTHONPATH=/app

RUN useradd -r -s /bin/false appuser && \
    chmod +x entrypoint.sh
USER appuser

CMD ["./entrypoint.sh"]
