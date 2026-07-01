# Runner Instructions

Runners are responsible for command construction and raw process execution.
They are not parsers and they are not ingestors.

## Rules

- Ordinary external tools must be declared in `cli_specs/` and executed through
  `GenericCliToolRunner`. Do not add per-tool wrapper classes for normal argv,
  stdin, timeout, parser, or stderr behavior.
- Concrete runner classes are reserved for real special cases such as browser
  orchestration or tools that need non-spec execution boundaries.
- New or modified execution paths should pass a validated `CommandInvocation`
  into `CommandExecutor`. Legacy `command/stdin/timeout` arguments are accepted
  only as compatibility until call sites are migrated.
- Do not write database state from runners.
- Do not write files directly from runners; raw artifact capture belongs in
  pipeline context.
- Do not accept raw command strings or arbitrary shell options from user input.
  Options must come from whitelisted capability profiles.
- Log command shape and counts, but avoid logging secrets or full sensitive
  payloads. Use command redaction and stdin summaries; never log raw stdin.
- Credential use must flow through opaque command `credential_refs` and a short-lived lease; do
  not place token material inside argv, stdin, logs, process events, parser
  payloads, raw artifact metadata, search documents, graph facts, or agent
  context. Raw secrets may exist only inside the secret store and runner-side
  injector after a valid lease is issued.
- Do not add user/agent supplied raw secret CLI options such as `--token`,
  `--cookie`, `--header`, `-H`, `--authorization`, or `--api-key` to runner
  command construction. Tools that truly require secret CLI flags must receive
  them only from the credential lease injector, and only when the capability
  profile declares bounded `allowed_cli_flags` with `allow_argv_exposure=true`.

- Runner injection code must resolve secret material through `CredentialLeaseService`; storage backends are not a runner API.


Credential materialization boundary:
- Runner-side secret materialization must go through `CredentialMaterializationPlan`.
- The plan may contain secret argv/env/header/temp-file data and must stay inside the execution boundary.
- Env materialization must enter execution through `CommandInvocation(env=...)`; `CommandExecutor` merges this as an overlay over the inherited process environment and logs only env names.
- Logs and process events must use the plan audit view or redacted command view, never raw plan fields.
- Concrete runners should not build secret CLI args directly from action options.


Credential storage may use `LocalEncryptedSecretCodec` for encrypted Postgres blobs, but runners still receive secret material only through lease resolution and materialization boundaries. Do not read `CREDENTIAL_MASTER_KEY` or decode secret versions inside runner code.

Credential backend composition lives outside runners: use `build_credential_secret_codec(...)` / `build_postgres_credential_store(...)` at application composition boundaries. Runners must not construct credential stores, read `CREDENTIAL_MASTER_KEY`, choose plaintext codecs, or decode secret versions directly.
