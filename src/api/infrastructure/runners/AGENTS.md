# Runner Instructions

Runners are responsible for command construction and raw process execution.
They are not parsers and they are not ingestors.

## Rules

- New CLI runners should expose `run_raw()` that yields raw `ProcessEvent`
  objects from `CommandExecutor`.
- A temporary `run()` compatibility wrapper may parse through the official
  parser, but live pipeline workers should use `run_raw()` plus explicit parser
  configuration.
- Do not write database state from runners.
- Do not write files directly from runners; raw artifact capture belongs in
  pipeline context.
- Do not accept raw command strings or arbitrary shell options from user input.
  Options must come from whitelisted capability profiles.
- Log command shape and counts, but avoid logging secrets or full sensitive
  payloads.
