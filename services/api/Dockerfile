FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt psycopg[binary]==3.2.3
COPY services/api /app/services/api
COPY packages/python-sdk /app/packages/python-sdk
ENV PYTHONPATH=/app/services/api:/app/packages/python-sdk
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
