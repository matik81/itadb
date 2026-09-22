FROM python:3.13-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:0.12.17 /uv /uvx /bin/
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable

FROM python:3.13-slim
RUN groupadd --gid 10001 itadb && useradd --uid 10001 --gid itadb --create-home itadb
WORKDIR /app
COPY --from=builder --chown=itadb:itadb /app/.venv /app/.venv
COPY --chown=itadb:itadb alembic.ini ./
COPY --chown=itadb:itadb migrations ./migrations
COPY --chown=itadb:itadb scripts ./scripts
COPY --chown=itadb:itadb contracts ./contracts
COPY --chown=itadb:itadb tests/fixtures ./tests/fixtures
RUN mkdir /app/data && chown itadb:itadb /app/data
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
USER itadb
EXPOSE 8000
CMD ["uvicorn", "itadb.api.app:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
