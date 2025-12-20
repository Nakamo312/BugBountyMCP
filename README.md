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

## Status

- [x] Domain Layer
- [ ] Infrastructure Layer
- [ ] Application Layer
- [ ] Presentation Layer
