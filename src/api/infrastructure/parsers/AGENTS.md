# Parser Instructions

Parsers convert raw process/event artifacts into normalized records. They must
be deterministic and replayable.

## Rules

- Parsers should accept raw `ProcessEvent` streams or raw artifact files and
  return normalized records/events.
- Parsers must not write to Postgres, publish events, or call external tools.
- Keep parser behavior conservative: ignore banners/noise instead of guessing.
- Tool-specific formats belong in explicit parser classes, not in runners or
  batch processors.
- Parser changes should include replay-style tests using representative raw
  stdout/stderr lines.
- Avoid universal parsers for tools with context-sensitive formats. Use
  tool-specific parsers when host, target, or mode context matters.
