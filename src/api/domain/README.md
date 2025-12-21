# Доменный слой (Domain Layer)

## 🟢 Слой 1: Чистое ядро без зависимостей

### Структура

```
domain/
├── __init__.py          # Экспорты
├── entities.py          # Все доменные модели и enums
├── repositories.py      # Абстрактные интерфейсы
└── README.md
```

### Принципы

1. **Никаких внешних зависимостей** - только Python stdlib
2. **Только dataclasses** - чистые данные
3. **Абстрактные репозитории** - интерфейсы без реализации
4. **Enums для типобезопасности**

### Entities (entities.py)

Все доменные модели:

- **Enums**: `RuleType`, `InputType`, `HttpMethod`, `ParamLocation`, `FindingState`, `ScanStatus`, `Severity`
- **Types**: `VulnType`, `LeakType`
- **Core**: `Program`, `ScopeRule`, `RootInput`, `Host`, `IPAddress`, `HostIP`, `Service`, `Endpoint`
- **Enrichment**: `InputParameter`, `Header`
- **Scanning**: `ScannerTemplate`, `ScannerExecution`, `Payload`
- **Results**: `Finding`, `Leak`

### Repositories (repositories.py)

Абстрактные интерфейсы (ABC) для всех сущностей:

- `IProgramRepository`
- `IHostRepository`
- `IEndpointRepository`
- `IFindingRepository`
- `ILeakRepository`
- И т.д.

### Пример использования

```python
from api.domain import Program, Host, IProgramRepository

# Доменная модель
program = Program(name="HackerOne")

# Использование через интерфейс (реализация будет в infrastructure)
async def create_program(repo: IProgramRepository, name: str):
    program = Program(name=name)
    return await repo.create(program)
```

### Важно

- ❌ НЕТ SQLAlchemy моделей
- ❌ НЕТ HTTP зависимостей
- ❌ НЕТ конфигов БД
- ✅ Только бизнес-логика
- ✅ Только типы данных
- ✅ Только интерфейсы
