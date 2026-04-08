FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create persistent data directory
RUN mkdir -p /app/data

EXPOSE 8300

# Entrypoint script patches config.yaml with LM_STUDIO_URL at runtime
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["uvicorn", "indauto.app:app", "--host", "0.0.0.0", "--port", "8300"]
