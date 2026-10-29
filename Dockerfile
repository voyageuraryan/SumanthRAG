# Dependencies only; the repo is bind-mounted at /app (see docker-compose.yml) so results/, reports/ and
# eval/ land on the host and git_commit/code_sha in run records are real.
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.12.5 /uv /usr/local/bin/uv
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
ENV UV_PROJECT_ENVIRONMENT=/opt/venv UV_LINK_MODE=copy PATH="/opt/venv/bin:$PATH" \
    PYTHONUTF8=1 PYTHONIOENCODING=utf-8 PYTHONUNBUFFERED=1
WORKDIR /app
ARG DENSE=false
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-install-project $( [ "$DENSE" = "true" ] && echo "--extra dense" )
RUN git config --system --add safe.directory /app
EXPOSE 8000
CMD ["uvicorn", "src.api:app", "--host", "0.0.0.0", "--port", "8000"]
