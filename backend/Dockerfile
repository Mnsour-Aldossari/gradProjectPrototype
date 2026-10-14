# Backend image (FastAPI + simulator + detection engine). NOT built or run yet - see README.
FROM python:3.14-slim

# DejaVu Sans has Arabic letters, for the PDF report (app/report/fonts.py).
RUN apt-get update && apt-get install -y --no-install-recommends fonts-dejavu-core && rm -rf /var/lib/apt/lists/*

WORKDIR /app
# requirements.lock pins every package (and what they need) to an exact version and hash, made from requirements.txt
# with: uv pip compile requirements.txt --generate-hashes --python-version 3.14 --python-platform x86_64-manylinux_2_28
#       --only-binary :all: --no-header -o requirements.lock
# Wheels only: no package runs a setup script while it is installed.
COPY requirements.lock .
RUN pip install --no-cache-dir --only-binary :all: --require-hashes -r requirements.lock

COPY app ./app
COPY migrations ./migrations
COPY alembic.ini .
COPY scripts ./scripts

# SQLite file and the generated signing key live in /data so a volume keeps them between container restarts.
ENV DATABASE_URL=sqlite:////data/uav.db \
    SECRET_KEY_FILE=/data/.secret_key
# The server does not need root. /data is made and owned by this user before VOLUME, so a new volume starts writable.
RUN useradd --system --uid 10001 --no-create-home uav && mkdir -p /data && chown uav:uav /data
VOLUME /data
USER uav
EXPOSE 8000
# The backend has no published port: only the web container's nginx reaches it, and it sets X-Forwarded-For, so the
# client address (used by the login throttle) is the visitor's and not nginx's.
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--forwarded-allow-ips", "*"]
