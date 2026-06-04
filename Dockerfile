FROM python:3.12-slim

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends build-essential && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY app ./app
COPY init_db.py ./
COPY migrations ./migrations
COPY alembic.ini ./

RUN pip install --no-cache-dir -e .

RUN mkdir -p /app/data /data
ENV PYTHONUNBUFFERED=1
ENV POLARIS_DB_PATH=/data/polaris.db
ENV POLARIS_RESULTS_DIR=/data/results

COPY scripts/railway-start.sh /app/scripts/railway-start.sh
RUN chmod +x /app/scripts/railway-start.sh

EXPOSE 8080
# Railway injects PORT; script runs init_db then uvicorn.
CMD ["/app/scripts/railway-start.sh"]
