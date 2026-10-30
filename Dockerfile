FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir . && useradd --create-home meetpoint \
    && mkdir -p /app/.local && chown meetpoint:meetpoint /app/.local
COPY alembic.ini ./
COPY migrations ./migrations
COPY scripts ./scripts
USER meetpoint
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM runtime AS tests
USER root
RUN pip install --no-cache-dir ".[dev]"
COPY tests ./tests
USER meetpoint
CMD ["python", "-m", "pytest", "-p", "no:cacheprovider"]
