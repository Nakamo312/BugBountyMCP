# Credential Reference Boundary

Status: accepted boundary for future credential lease implementation

Date: 2026-06-28

## Purpose

Some authorized scans and HTTP requests will need authentication material:
headers, cookies, bearer tokens, API keys, session identifiers, or temporary
program credentials. The system must support those actions without exposing raw
secret material to agents, LLM context, proposal payloads, logs, artifacts,
OpenSearch documents, Neo4j properties, or dashboard read models.

The approved boundary is:

```text
agent/proposal/action options
  -> opaque credential_ref
  -> ActionService policy/scope/approval/budget checks
  -> short-lived credential lease
  -> runner-local injection at execution time
  -> artifact/log/process-event sanitization
```

Agents and proposals may refer to a credential by an opaque reference. They must
not receive the token, cookie, header value, or API key itself.

## Current State

The action option boundary now has typed metadata for authenticated actions:

```text
credential_ref
auth_injection
```

`credential_ref` is an opaque identifier such as
`credref:program/acme/session/low_priv`. It is not a token, cookie, password,
header value, or API key.

`auth_injection` describes only where a future lease injector should place the
secret at execution time. Supported modes are:

```text
header
cookie
cookie_jar
env
cli_flag
cli_flag_equals
config_file
browser_context
mtls_cert
proxy_auth
```

`cli_flag` and `cli_flag_equals` are allowed because some tools only accept
secret material through explicit CLI parameters. They still must not receive raw
secrets from agents or action options. A profile must explicitly opt in to argv
exposure and enumerate the allowed flags before those modes validate.

Example action options:

```json
{
  "credential_ref": "credref:program/acme/session/low_priv",
  "auth_injection": {
    "mode": "header",
    "slot": "Authorization"
  }
}
```

The option normalizer rejects raw credential-looking options such as
`authorization`, `cookie`, `token`, `api_key`, and values such as
`Authorization: Bearer ...`. Authenticated scans should declare
`credential_ref` and `auth_injection` in the profile option schema instead.

`CommandInvocation` is the infrastructure-level process execution contract. It
carries:

```text
argv
stdin
timeout
env overlay
credential_refs
```

`env` in `CommandInvocation` is an overlay on top of the inherited process
environment, not a complete replacement. This keeps PATH/tool discovery stable
while allowing runner-local env materialization. Env values are secret-bearing
when produced by credential materialization; logs and audit events may show only
variable names with redacted values.

`credential_refs` in `CommandInvocation` are still opaque strings. They do not
resolve secrets yet. They exist so runners and command execution paths have a
stable place for future leases without pushing credentials into application
core objects or free-form command arguments.

The current implementation now includes the storage foundation for that boundary:

```text
credential_refs
credential_secret_versions
credential_leases
```

`credential_refs` stores public registry metadata: program, opaque ref, identity
label, kind, scope, status, expiry, and non-secret metadata.

`credential_secret_versions` stores only encrypted/local secret pointers such as
`ciphertext`, `nonce`, `key_id`, or `external_secret_ref`; raw secret values must
not be copied into logs, audit metadata, graph facts, search documents, or agent
state. Local/dev code may use the in-memory test store, but production storage
should use encrypted Postgres blobs or an external vault/KMS-backed backend.

`credential_leases` stores short-lived lease metadata: purpose, capability,
target scope, `auth_injection`, status, expiry, and audit metadata. A lease is
not the secret. It is the permission record that allows a runner-side injector
to materialize the secret for one approved execution.

`CredentialLeaseService` is now the application-level boundary for issuing and
resolving leases. Storage backends keep defensive checks, but callers should not
issue leases or resolve secret material by talking to stores directly. The service
applies TTL caps, purpose/capability/target binding, argv-exposure policy for
CLI materialization, and audit-safe lease views.

The runner-side materialization contract now exists as
`CredentialMaterializationPlan`. It converts already-leased `SecretMaterial` plus
`auth_injection` metadata into runner-local additions: argv entries, env entries,
request headers/cookies/proxy metadata, or temp-file descriptors. These plans may
carry secret values and therefore must remain inside the runner execution
boundary. Their repr, audit views, and redacted command views must not expose the
secret.

The command executor can now carry an env overlay through `CommandInvocation`
and passes that overlay to subprocesses after merging it with `os.environ`. This
is executor-level support only: concrete runners are still not wired to resolve
leases or materialize secrets automatically.

A DB-backed credential store now exists as `PostgresCredentialStore`. It uses
SQLAlchemy Core against `credential_refs`, `credential_secret_versions`, and
`credential_leases`; it never chooses a plaintext codec by default. Application
composition must go through `build_credential_secret_codec(...)` /
`build_postgres_credential_store(...)`, which read credential backend settings
and wire an explicit `SecretCodec`. The default backend is encrypted Postgres
(`CREDENTIAL_SECRET_BACKEND=postgres_encrypted`) and requires
`CREDENTIAL_MASTER_KEY` plus `CREDENTIAL_KEY_ID`. Tests/dev may explicitly opt
into `DevOnlyPlaintextSecretCodec` only with
`CREDENTIAL_SECRET_BACKEND=dev_plaintext` and
`CREDENTIAL_ALLOW_DEV_PLAINTEXT=true`. Local encrypted Postgres storage uses
`LocalEncryptedSecretCodec`, which stores AES-GCM ciphertext/nonce/key metadata in
Postgres and requires a 32-byte master key outside the database. The DB store
stores encoded payloads only and reconstructs `SecretMaterial` only during lease
resolution.

The current cleanup still has not connected materialization to concrete runners,
UI, or an external Vault/KMS backend. Those belong to the next credential lease
patches.

## Rules

Raw credentials must not be placed in:

```text
argv
stdin
runner logs
ProcessEvent payloads
parser payloads
raw artifact metadata
agent-facing OpenSearch documents
Neo4j GraphFacts
LangGraph state
proposal explanations
```

Runner code must not add direct CLI options such as:

```text
--token
--cookie
--header
-H
--authorization
--api-key
```

If a tool needs authenticated execution, the action profile should expose
`credential_ref` plus `auth_injection` metadata, and the runner should receive
only opaque credential refs. The future credential injector should materialize
the secret only inside the execution boundary.

Direct CLI secret flags are not globally forbidden as a materialization
mechanism; they are forbidden as user/agent supplied raw options. A profile may
allow a CLI flag only by declaring `auth_injection` with `allowed_modes` including
`cli_flag` or `cli_flag_equals`, `allow_argv_exposure=true`, and a bounded
`allowed_cli_flags` list such as `--api-token`. Prefer env/config-file/cookie-jar
materialization when a tool supports safer channels.

Logging may show command shape after redaction. It must not show stdin payloads
or credential material.

## Future Lease Layer

The next implementation should add concrete runner-side injection with these
properties:

```text
credential_ref -> CredentialLeaseService -> policy-bound lease -> runner-local materialization
```

Expected responsibilities:

- bind credentials to program/scope/purpose;
- enforce TTL and single-purpose use through `CredentialLeaseService`;
- keep secret material encrypted at rest or delegated to an external secret
  backend;
- expose only opaque refs to agents and proposals;
- inject secrets into tools only after ActionService policy/scope/approval/budget
  checks pass;
- redact secret material from logs, artifacts, parser output, search documents,
  graph facts, and agent context;
- audit credential lease use without storing the secret value in the audit log.

## Non-Goals

This boundary does not make agents trusted with credentials. It also does not
turn credential use into a bypass around the action control plane. Authenticated
actions remain normal actions: they must pass scope, policy, approval, budgets,
and runner capability validation.

## Secret Version Lifecycle And Refresh Metadata

`credential_ref` is the stable identity handle. Secret material behind that ref
is versioned. Refreshing a session cookie, rotating an API key, or replacing an
OAuth access token must create a new `credential_secret_versions` row and update
`credential_refs.current_secret_version_id`; callers continue to use the same
opaque `credential_ref`.

The lifecycle fields are:

```text
credential_refs.current_secret_version_id
credential_refs.refresh_policy_json
credential_refs.refresh_status
credential_refs.last_refreshed_at
credential_refs.next_refresh_at
credential_secret_versions.expires_at
credential_secret_versions.replaced_by_version_id
```

New leases may only use the current active, unexpired secret version. Old
versions are retained for audit/history, but they are not selected for new lease
issuance after rotation or explicit expiry. Refresh metadata is public scheduling
metadata and must not contain raw tokens, cookies, Authorization headers,
passwords, or session values.


## Local Encrypted Postgres Codec

`LocalEncryptedSecretCodec` is the self-contained encrypted storage backend for
local/dev/prod-lite deployments that do not yet run Vault/KMS. It uses
AES-256-GCM through the `cryptography` package. The database stores:

```text
storage_backend = postgres_encrypted_aesgcm
ciphertext
nonce
key_id
metadata_json.algorithm = AES-256-GCM
metadata_json.content_type
```

The master key must be injected from outside Postgres, normally through
`CREDENTIAL_MASTER_KEY` as URL-safe base64 for exactly 32 bytes. It must not be
stored in migrations, fixtures, docs, logs, action options, or DB rows.

This backend is not a replacement for a managed secret service. It is a practical
working encrypted backend that keeps plaintext out of Postgres while preserving
the `SecretCodec` interface. Vault/KMS/Secrets Manager adapters can be added as
new codecs without changing `PostgresCredentialStore`.

Credential backend composition is controlled by these settings:

```text
CREDENTIAL_SECRET_BACKEND=postgres_encrypted | local_encrypted | dev_plaintext
CREDENTIAL_MASTER_KEY=<base64 32 bytes, required for encrypted backends>
CREDENTIAL_KEY_ID=<audit/key label>
CREDENTIAL_ALLOW_DEV_PLAINTEXT=false
```

`dev_plaintext` is never a fallback. It must be selected explicitly and requires
`CREDENTIAL_ALLOW_DEV_PLAINTEXT=true`, so a missing master key fails closed rather
than silently storing secrets in plaintext.

## Credential management API/service boundary

`CredentialManagementService` is the audit-safe human/API boundary for stable identity refs and secret version lifecycle. It may accept raw secret material only in a rotation request, immediately converts it to `SecretMaterial`, and returns only redacted metadata. It does not resolve leases, materialize runner env/argv/temp files, call `CredentialLeaseService.resolve_secret_for_runner`, or expose the configured `SecretCodec`.

REST wiring lives under `/api/v1/credentials`:

- `POST /api/v1/credentials` registers a stable `credential_ref` identity record without secret material.
- `POST /api/v1/credentials/rotate-secret` stores a new secret version behind an existing ref and returns only audit-safe metadata.
- `POST /api/v1/credentials/expire-current-secret` marks the current version expired and sets the ref to `refresh_due`.
- `GET /api/v1/credentials` and `GET /api/v1/credentials/metadata` return audit-safe metadata only.

This is the place to create `user_a`, `user_b`, `admin`, `expired_user`, and similar identities for IDOR/authz comparisons. The API never returns submitted secret values; authenticated execution still requires a later lease plus runner-side materialization.
