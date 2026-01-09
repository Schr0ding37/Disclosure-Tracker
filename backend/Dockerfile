FROM python:3.10-slim
WORKDIR /app
# 安裝編譯所需的系統套件及 Python 必要套件
RUN apt-get update && apt-get install -y libpq-dev gcc && \
    pip install --no-cache-dir fastapi uvicorn requests psycopg2-binary
COPY . .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]