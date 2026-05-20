# Ingestor Instructions

Ingestors persist normalized records into domain state and return only newly
discovered facts needed for deterministic follow-up events.

## Rules

- Ingestors receive normalized records, not raw CLI stdout.
- Do not execute tools or parse raw scanner output here.
- Use unit-of-work boundaries and savepoints for partial batch failure where
  existing patterns do.
- Return new entities through `IngestResult`; do not emit event-bus messages
  directly from ingestors.
- Keep deduplication and scope-sensitive materialization explicit and tested.
- Batch failures should roll back the batch, not the whole scan, unless the
  surrounding contract explicitly requires it.
