FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code and tests
COPY src/ ./src/
COPY tests/ ./tests/

EXPOSE 8000

CMD ["python", "-m", "src.cli", "serve", "--port", "8000", "--host", "0.0.0.0"]
