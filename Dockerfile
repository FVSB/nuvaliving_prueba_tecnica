FROM python:3.12-slim-bookworm

# Same uv version as the registered development environment.
RUN python -m pip install --no-cache-dir uv==0.9.24
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY src ./src
COPY config ./config
RUN uv sync --frozen --no-dev --no-editable && mkdir -p /app/traces

ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 TRACES_DIR=/app/traces \
    BUSINESS_RULES_PATH=/app/config/business_rules.json
ENTRYPOINT ["maintenance-agent"]
