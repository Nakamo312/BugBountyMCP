FROM mcr.microsoft.com/playwright/python:v1.48.0-jammy

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    python -m playwright install chromium

COPY scanner.proto .
RUN python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. scanner.proto

COPY playwright_scanner.py .
COPY playwright_service.py .

EXPOSE 50051

CMD ["python", "playwright_service.py"]
