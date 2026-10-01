# Backend image (FastAPI + simulator + detection engine). NOT built or run yet - see README.
FROM python:3.14-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY scripts ./scripts

# SQLite file lives in /data so a volume can keep it between container restarts.
ENV DATABASE_URL=sqlite:////data/uav.db
VOLUME /data
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
