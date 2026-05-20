# Pipeline Instructions

The pipeline is a declarative event-driven graph. YAML declares workers,
capabilities, events, profiles, and parser stages.

## Worker Flow

Generic scan workers should follow this order:

1. Extract targets from the incoming event.
2. Resolve runner, parser, processor, and ingestor from the whitelisted catalog.
3. Call `runner.run_raw()` when a parser is configured.
4. Capture the raw stream through `PipelineContext.capture_raw_stream`.
5. Normalize through the configured parser.
6. Batch normalized records.
7. Ingest normalized state.
8. Emit deterministic events from `IngestResult`.

## Rules

- Do not parse CLI output inside `ScanNode`.
- Do not bypass raw artifact capture for CLI-backed workers.
- Do not add unregistered component names to YAML. Add them to the catalog and
  tests.
- Keep event names stable. New event names need routing and contract tests.
- Custom nodes such as FFUF, Amass, and Hakip2Host must preserve the same
  runner/raw/parser/ingestor boundary even when they cannot use `ScanNode`.
- Compatibility with old `nodes:` YAML exists only for migration. Prefer
  `workers:`.
