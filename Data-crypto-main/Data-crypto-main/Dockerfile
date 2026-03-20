# Stage 1: Builder
FROM python:3.11-slim as builder

# Set work directory
WORKDIR /app

# Install build dependencies required for compiling some Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file
COPY requirements.txt .

# Build wheels for all dependencies to optimize the final image size
RUN pip wheel --no-cache-dir --no-deps --wheel-dir /app/wheels -r requirements.txt

# Stage 2: Runtime
FROM python:3.11-slim

# Set environment variables to prevent Python from writing pyc files and buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install runtime dependencies ONLY (e.g., libpq5 for psycopg2 if used)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy wheels from the builder stage
COPY --from=builder /app/wheels /wheels
COPY --from=builder /app/requirements.txt .

# Install dependencies from the built wheels without using cache
RUN pip install --no-cache /wheels/* \
    && rm -rf /wheels

# Copy application code
COPY . /app

# Create a non-root user for security purposes
RUN addgroup --system appgroup && adduser --system --group appuser \
    && chown -R appuser:appgroup /app
USER appuser

# Expose the API port
EXPOSE 8000

# Command to run the application using uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
