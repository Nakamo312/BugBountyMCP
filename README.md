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

Запуск приложения:

```bash
python main.py
```

Или через uvicorn напрямую:

```bash
uvicorn api.presentation.rest.app:create_app --factory --host 0.0.0.0 --port 8000
```

Приложение будет доступно по адресу `http://localhost:8000`

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
