# Artifact Instructions

Artifacts preserve raw tool output for replay, audit, and parser development.

## Rules

- Store large raw payloads in file/object storage, not inline database columns.
- Use Postgres only as an index for artifact metadata.
- Metadata should include program/job/run context, node/event names,
  `storage_uri`, `sha256`, `size_bytes`, artifact type, and parser metadata.
- Writes should be streaming and should avoid holding full scanner output in
  memory.
- Prefer temp-file write plus atomic rename for filesystem artifacts.
- Parser replay must work from `storage_uri` without rerunning the scanner.
