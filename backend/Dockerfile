FROM python:3.10-slim
WORKDIR /app
# 安裝編譯所需的系統套件及 Python 必要套件
COPY requirements.txt .
RUN apt-get update && apt-get install -y libpq-dev gcc && \
    pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]