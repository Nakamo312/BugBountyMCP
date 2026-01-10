# Pipeline Architecture

Refactored orchestrator using **Pipeline Nodes** pattern.

## Принцип

Каждое событие обрабатывается отдельной нодой. Orchestrator — тупой диспетчер.

```
Event → Orchestrator → NodeRegistry → Node.process() → emit Events
```

## Структура

```
pipeline/
├── base.py              # PipelineNode, PipelineContext
├── registry.py          # NodeRegistry (EventType → Node)
├── scope_policy.py      # ScopePolicy (фильтрация доменов)
├── bootstrap.py         # build_node_registry()
└── nodes/
    ├── tlsx_node.py             # TLSX_RESULTS_BATCH → CERT_SAN_DISCOVERED
    ├── naabu_node.py            # NAABU_RESULTS_BATCH → PORTS_DISCOVERED
    ├── ports_discovered_node.py # PORTS_DISCOVERED → HTTPx baseline
    ├── subdomain_discovered_node.py
    ├── dnsx_basic_node.py
    ├── httpx_results_node.py
    ├── ingestor_nodes.py        # Простые инжестор-ноды
    └── asn_track_nodes.py       # ASN Track специфичные ноды
```

## Ключевые абстракции

### PipelineNode

```python
class PipelineNode(ABC):
    event_in: EventType
    event_out: list[EventType]

    async def process(self, event: Dict[str, Any]) -> None:
        # Логика обработки
        await self.ctx.emit(EventType.NEXT_EVENT, payload)
```

**Правила:**
- Нода НЕ знает про EventBus (использует `ctx.emit`)
- Нода НЕ фильтрует scope напрямую (использует `ctx.scope`)
- Нода НЕ управляет DI (использует `ctx.container`)

### PipelineContext

Контекст с доступом к:
- `bus` - EventBus
- `container` - DI container
- `scope` - ScopePolicy
- `_scan_semaphore` - Rate limiting

```python
await ctx.emit(EventType.FOO, payload)
await ctx.scope.filter_domains(program_id, domains)
async with ctx.acquire_scan_slot():
    # Rate-limited scan
```

### ScopePolicy

Централизованная фильтрация scope:

```python
in_scope, out = await ctx.scope.filter_domains(program_id, domains)
```

**Важно:** Scope применяется ТОЛЬКО к доменам (DNS Track), НЕ к IP (ASN Track independence).

### NodeRegistry

```python
registry.register(TLSxCertNode(ctx))
node = registry.get(EventType.TLSX_RESULTS_BATCH)
```

## Пример: TLSx Node

```python
class TLSxCertNode(PipelineNode):
    event_in = EventType.TLSX_RESULTS_BATCH
    event_out = [EventType.CERT_SAN_DISCOVERED]

    async def process(self, event: Dict[str, Any]) -> None:
        domains = extract_domains_from_certs(event["results"])

        if domains:
            await self.ctx.emit(
                EventType.CERT_SAN_DISCOVERED,
                {"program_id": event["program_id"], "domains": domains}
            )
```

## Orchestrator

**Было:** 851 строка god-object
**Стало:** 102 строки тупой диспетчер

```python
class Orchestrator:
    def __init__(self, bus, container, settings):
        self.registry = build_node_registry(bus, container, settings)

    async def _dispatch_to_node(self, event_type, event):
        node = self.registry.get(event_type)
        await node.process(event)
```

## Как добавить новую ноду

1. Создать класс в `nodes/`:
```python
class MyNewNode(PipelineNode):
    event_in = EventType.MY_EVENT
    event_out = [EventType.NEXT_EVENT]

    async def process(self, event):
        # Логика
        pass
```

2. Добавить в `nodes/__init__.py`

3. Зарегистрировать в `bootstrap.py`:
```python
registry.register(MyNewNode(ctx))
```

## Архитектурные принципы

### DNS Track (домены)
```
Subfinder → SUBDOMAIN_DISCOVERED
         → SubdomainDiscoveredNode (scope filter)
         → DNSx Basic → DNSX_BASIC_RESULTS_BATCH
         → DNSxBasicResultsNode (wildcard filter)
         → DNSX_FILTERED_HOSTS
         → DNSxFilteredHostsNode
         → HTTPx
```

### ASN Track (инфраструктура)
```
ASNMap → CIDR_DISCOVERED
      → CIDRDiscoveredNode
      → MapCIDR → IPS_EXPANDED
      → IPsExpandedNode
      → Naabu + TLSx (parallel)
      → NAABU_RESULTS_BATCH, TLSX_RESULTS_BATCH
      → NaabuPortsNode → PORTS_DISCOVERED
      → PortsDiscoveredNode → HTTPx baseline

TLSxCertNode → CERT_SAN_DISCOVERED (только токены, НЕ фильтр IP)
```

## Преимущества

✅ **Модульность:** Каждая нода — независимая единица логики
✅ **Тестируемость:** Ноды тестируются изолированно
✅ **Читаемость:** Pipeline читается как граф в `bootstrap.py`
✅ **Расширяемость:** Добавить ноду = 1 класс + 1 строка регистрации
✅ **Separation of Concerns:** Orchestrator ничего не знает про бизнес-логику

## Migration Guide

**Старый код:**
```python
async def handle_tlsx_results_batch(self, event):
    # 40 строк логики + scope + bus + container
```

**Новый код:**
```python
class TLSxCertNode(PipelineNode):
    event_in = EventType.TLSX_RESULTS_BATCH
    event_out = [EventType.CERT_SAN_DISCOVERED]

    async def process(self, event):
        domains = extract_domains(event)
        await self.ctx.emit(EventType.CERT_SAN_DISCOVERED, domains)
```
