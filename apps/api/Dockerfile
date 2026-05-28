FROM python:3.12-slim

WORKDIR /workspace/apps/api

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    TZ=Asia/Shanghai

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --frozen
RUN uv run playwright install --with-deps chromium

COPY app ./app

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
