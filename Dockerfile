FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    libpcap-dev \
    ca-certificates \
    git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

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

RUN chmod +x entrypoint.sh

RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

ENTRYPOINT ["./entrypoint.sh"]
CMD ["python", "main.py"]