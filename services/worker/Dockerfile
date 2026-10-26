FROM python:3.11-slim@sha256:b7a9e5f6a93d6d4a31f129bbd4bdee69efccb6ded0fb230d78aafaf37af98377

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY packages/python-sdk /app/packages/python-sdk
COPY services/worker/spantrace_worker.py /app/spantrace_worker.py
ENV PYTHONPATH=/app:/app/packages/python-sdk
USER 1000:1000
ENTRYPOINT ["python", "-m", "spantrace_worker"]
