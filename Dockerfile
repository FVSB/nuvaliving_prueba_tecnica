FROM python:3.12-slim-bookworm

# Same uv version as the registered development environment.
RUN python -m pip install --no-cache-dir uv==0.9.24
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable

ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 TRACES_DIR=/app/traces
ENTRYPOINT ["maintenance-agent"]
