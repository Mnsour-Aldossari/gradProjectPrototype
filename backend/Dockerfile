# Backend image (FastAPI + simulator + detection engine). NOT built or run yet - see README.
FROM python:3.14-slim

# DejaVu Sans has Arabic letters, for the PDF report (app/report/fonts.py).
RUN apt-get update && apt-get install -y --no-install-recommends fonts-dejavu-core && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY migrations ./migrations
COPY alembic.ini .
COPY scripts ./scripts

# SQLite file lives in /data so a volume can keep it between container restarts.
ENV DATABASE_URL=sqlite:////data/uav.db
VOLUME /data
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
