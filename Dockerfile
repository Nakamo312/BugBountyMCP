FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    libpcap-dev \
    ca-certificates \
    git \
    wget \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir waymore

RUN git clone https://github.com/GerbenJavado/LinkFinder.git /opt/linkfinder && \
    cd /opt/linkfinder && \
    pip install -r requirements.txt && \
    echo '#!/bin/bash\ncd /opt/linkfinder && python linkfinder.py "$@"' > /usr/local/bin/linkfinder && \
    chmod +x /usr/local/bin/linkfinder && \
    chmod +x /opt/linkfinder/linkfinder.py

COPY src/ ./src/
COPY main.py .
COPY alembic/ ./alembic/
COPY alembic.ini .
COPY entrypoint.sh .

RUN python -m grpc_tools.protoc -I./src/api/infrastructure/proto --python_out=./src/api/infrastructure/runners --grpc_python_out=./src/api/infrastructure/runners ./src/api/infrastructure/proto/scanner.proto

RUN chmod +x entrypoint.sh

RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app

RUN mkdir -p /home/appuser/.config/katana /home/appuser/.cache/rod && \
    chown -R appuser:appuser /home/appuser/.config /home/appuser/.cache

USER appuser

EXPOSE 8000

ENTRYPOINT ["./entrypoint.sh"]
CMD ["python", "main.py"]