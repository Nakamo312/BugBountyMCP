# Tests

## Overview

Comprehensive test suite for Bug Bounty MCP framework covering:
- Repository layer (database operations)
- Service layer (business logic)
- Integration tests (end-to-end workflows)

## Structure

```
tests/
├── conftest.py              # Global fixtures (DB engine, session, program)
├── repositories/            # Repository tests
│   ├── conftest.py          # Repository-specific fixtures
│   ├── test_host_repository.py
│   ├── test_ip_address_repository.py
│   ├── test_endpoint_repository.py
│   └── ...
└── services/                # Service tests
    ├── conftest.py          # Service-specific fixtures
    ├── test_httpx_service_scan.py
    └── test_subfinder_service.py
```

## Running Tests

### Run all tests
```bash
pytest tests/
```

### Run specific test file
```bash
pytest tests/repositories/test_host_repository.py
```

### Run specific test class
```bash
pytest tests/services/test_httpx_service_scan.py::TestHTTPXScanServiceModel
```

### Run specific test method
```bash
pytest tests/services/test_httpx_service_scan.py::TestHTTPXScanServiceModel::test_execute_stores_data_in_db
```

### Run with coverage
```bash
pytest --cov=src tests/
```

### Run with detailed output
```bash
pytest -v tests/
```

### Run with print statements visible
```bash
pytest -s tests/
```

## Test Database

Tests use **SQLite in-memory database** for isolation and speed:
- Each test gets a fresh database
- No persistent state between tests
- PostgreSQL-specific types are mocked for SQLite compatibility

## Fixtures

### Global Fixtures (tests/conftest.py)
- `engine` - SQLAlchemy async engine with SQLite
- `session` - Async database session
- `program` - Test program instance
- `mock_settings` - Mocked Settings with test paths

### Repository Fixtures (tests/repositories/conftest.py)
- Individual repository instances for each entity type

### Service Fixtures (tests/services/conftest.py)
- `httpx_service` - HTTPXScanService with all dependencies
- `subfinder_service` - SubfinderScanService with dependencies
- Repository instances
- Mocked settings

## Writing New Tests

### Repository Test Template
```python
import pytest
from sqlalchemy import select

@pytest.mark.asyncio
class TestMyRepository:
    
    async def test_create(self, session, program):
        repo = MyRepository(session)
        entity = await repo.create({
            'program_id': program.id,
            'field': 'value'
        })
        await session.commit()
        
        assert entity.id is not None
        assert entity.field == 'value'
```

### Service Test Template
```python
import pytest
from unittest.mock import AsyncMock

@pytest.mark.asyncio
class TestMyService:
    
    async def test_execute(self, my_service, program, session):
        # Mock external tool execution
        async def mock_scan(*args, **kwargs):
            yield "result_line_1"
            yield "result_line_2"
        
        my_service.execute_scan = mock_scan
        
        # Execute service
        result = await my_service.execute(
            program_id=str(program.id),
            target="example.com"
        )
        await session.commit()
        
        # Verify results
        assert result["status"] == "success"
```

## Best Practices

1. **Use async fixtures**: Always use `@pytest_asyncio.fixture` for async fixtures
2. **Commit when needed**: Call `await session.commit()` after database operations
3. **Mock external tools**: Don't execute real tools in tests - mock `exec_stream`
4. **Test isolation**: Each test should be independent
5. **Clear assertions**: Use descriptive assertion messages
6. **Test edge cases**: Empty results, duplicates, errors

## Common Patterns

### Testing Deduplication
```python
# Create initial data
await repo.create({'program_id': program.id, 'value': 'duplicate'})
await session.commit()

# Attempt to create duplicate - should handle gracefully
await repo.upsert({'program_id': program.id, 'value': 'duplicate'})
```

### Testing Bulk Operations
```python
items = [
    {'program_id': program.id, 'field': f'value{i}'}
    for i in range(100)
]
await repo.bulk_upsert(items)
await session.commit()

# Verify count
result = await session.execute(select(func.count()).select_from(Model))
assert result.scalar() == 100
```

### Mocking Command Execution
```python
async def mock_exec_stream(*args, **kwargs):
    yield "line1"
    yield "line2"

service.exec_stream = mock_exec_stream

result = []
async for line in service.execute_scan("target"):
    result.append(line)
```

## Debugging Tests

### Show SQL queries
```bash
pytest tests/ -v --log-cli-level=DEBUG
```

### Drop into debugger on failure
```bash
pytest tests/ --pdb
```

### Run only failed tests
```bash
pytest tests/ --lf
```

## CI/CD

Tests are automatically run in GitHub Actions on:
- Push to main
- Pull requests
- Manual workflow dispatch

See `.github/workflows/CI.yml` for details.
