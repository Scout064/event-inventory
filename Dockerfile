# Use a lightweight Python runtime
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
# Must match WORKDIR so the entrypoint resolves all paths correctly
ENV APP_DIR=/inventory_app

WORKDIR /inventory_app

# Install mysql-client so the entrypoint can run mysql and mysqldump.
# default-mysql-client provides both; without this the entrypoint fails silently.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    default-mysql-client \
    libmariadb-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies system-wide (no venv needed in Docker)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Copy and wire up the entrypoint
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

# Entrypoint handles migrations then hands off to gunicorn via exec
ENTRYPOINT ["/docker-entrypoint.sh"]

# add labels
LABEL org.opencontainers.image.description="Web-based inventory system for event and production equipment"
