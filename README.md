# BB Framework - Bug Bounty Reconnaissance Framework

Clean Architecture with Domain-Driven Design

## Architecture

```
Domain Layer (Core)
  ↑
Infrastructure Layer (DB, Repositories)
  ↑
Application Layer (Services, Business Logic)
  ↑
Presentation Layer (REST, GraphQL)
```

## Structure

```
api/
├── domain/              # Core business logic (no dependencies)
│   ├── entities/        # Domain models
│   ├── enums/           # Enumerations
│   └── repositories/    # Abstract interfaces
│
├── infrastructure/      # Implementation details
│   ├── database/        # SQLAlchemy models
│   ├── repositories/    # Concrete repositories
│   └── normalization/   # urldedupe, anew logic
│
├── application/         # Business use cases
│   ├── services/        # Scan services
│   ├── dto/             # Data transfer objects
│   └── parsers/         # Tool output parsers
│
└── presentation/        # API layer
    ├── graphql/         # GraphQL API
    ├── rest/            # REST API
    └── schemas/         # Pydantic schemas
```

## Setup

```bash
pip install -r requirements.txt
```

## Running

### Local Development

Запуск приложения:

```bash
python main.py
```

Или через uvicorn напрямую (из корня проекта):

```bash
uvicorn src.api.presentation.rest.app:create_app --factory --host 0.0.0.0 --port 8000
```

Или с добавлением src в PYTHONPATH:

```bash
PYTHONPATH=src uvicorn api.presentation.rest.app:create_app --factory --host 0.0.0.0 --port 8000
```

На Windows PowerShell:
```powershell
$env:PYTHONPATH="src"; uvicorn api.presentation.rest.app:create_app --factory --host 0.0.0.0 --port 8000
```

Приложение будет доступно по адресу `http://localhost:8000`

### Docker Compose

Для запуска с Docker Compose (с персистентной БД и доступом к CLI инструментам хоста):

```bash
# Создать .env файл (если еще не создан)
cp .env.example .env

# Запустить сервисы
docker-compose up -d

# Просмотр логов
docker-compose logs -f api

# Остановить сервисы
docker-compose down
```

Подробная документация по Docker: [DOCKER.md](DOCKER.md)

**Важно**: Убедитесь, что CLI инструменты (httpx, subfinder, gau и т.д.) установлены на вашем хосте, так как контейнер использует их через bind mounts.

## API Endpoints

- `POST /scan/subfinder` - Запуск Subfinder сканирования
- `POST /scan/httpx` - Запуск HTTPX сканирования

## Dependency Injection

Проект использует **dishka** для Dependency Injection:

- **DatabaseProvider** - провайдер для подключения к БД
- **RepositoryProvider** - провайдер для репозиториев
- **ServiceProvider** - провайдер для сервисов

`SubfinderScanService` зависит только от `HTTPXScanService`, который уже имеет все зависимости на репозитории.

## Status

- [x] Domain Layer
- [x] Infrastructure Layer
- [x] Application Layer
- [x] Presentation Layer (REST API с DI)
