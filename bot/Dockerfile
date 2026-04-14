FROM python:3.12-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers

COPY shared/ /app/shared/
COPY bot/pyproject.toml ./
RUN uv pip install --system /app/shared/ && \
    uv pip compile pyproject.toml -o requirements.txt && \
    uv pip install --system -r requirements.txt && \
    rm requirements.txt && \
    playwright install --with-deps chromium

COPY bot/ .

RUN useradd -r -m -s /bin/false appuser && \
    chown -R appuser:appuser /app /opt/pw-browsers
USER appuser

CMD ["python", "main.py"]
