from __future__ import annotations

import ast
import re
from pathlib import Path

_RUNNER_DIR = Path("src/api/infrastructure/runners")
_DOC_PATHS = (
    Path("docs/architecture/credential-ref-boundary.md"),
    Path("docs/architecture/current-state-sync.md"),
    Path("HANDOFF_FOR_NEW_CHAT.md"),
    Path("src/api/infrastructure/runners/AGENTS.md"),
)
_FORBIDDEN_DIRECT_SECRET_OPTIONS = frozenset(
    {
        "-H",
        "--header",
        "--headers",
        "--authorization",
        "--auth",
        "--bearer",
        "--cookie",
        "--password",
        "--secret",
        "--session",
        "--token",
        "--api-key",
        "--apikey",
    }
)
_FORBIDDEN_INLINE_SECRET_PATTERN = re.compile(
    r"^(?:--?(?:authorization|auth|bearer|cookie|header|headers|password|secret|session|token|api[-_]?key)="
    r"|authorization:|cookie:|x-api-key:|api-key:|token:)",
    re.IGNORECASE,
)


def _string_literals(path: Path) -> list[str]:
    tree = ast.parse(path.read_text())
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]


def test_credential_ref_boundary_is_documented_in_current_handoff_and_runner_policy() -> None:
    for path in _DOC_PATHS:
        text = path.read_text()
        assert "credential_ref" in text or "credential_refs" in text, path
        assert "argv" in text, path
        assert "stdin" in text, path


def test_runner_command_literals_do_not_embed_direct_secret_options() -> None:
    offenders: list[str] = []

    for path in sorted(_RUNNER_DIR.glob("*.py")):
        for literal in _string_literals(path):
            if (
                literal in _FORBIDDEN_DIRECT_SECRET_OPTIONS
                or _FORBIDDEN_INLINE_SECRET_PATTERN.match(literal)
            ):
                offenders.append(f"{path}:{literal!r}")

    assert offenders == []


def test_runner_policy_points_to_lease_injection_instead_of_direct_secret_args() -> None:
    text = Path("src/api/infrastructure/runners/AGENTS.md").read_text()

    assert "credential_refs" in text
    assert "lease injector" in text
    assert "raw secret CLI options" in text


def test_credential_ref_action_option_contract_is_documented() -> None:
    text = Path("docs/architecture/credential-ref-boundary.md").read_text()

    assert "auth_injection" in text
    assert "header" in text
    assert "cookie_jar" in text
    assert "browser_context" in text
    assert "cli_flag" in text
    assert "allowed_cli_flags" in text
    assert "allow_argv_exposure" in text
    assert "Authorization: Bearer" in text
    assert "The option normalizer rejects raw credential-looking options" in text


def test_application_option_boundary_exposes_typed_credential_options() -> None:
    text = Path("src/api/application/execution_limits.py").read_text()

    assert "credential_ref" in text
    assert "auth_injection" in text
    assert "reject_raw_credential_option" in text


def test_auth_injection_profile_policy_exposes_cli_flag_boundaries() -> None:
    text = Path("src/api/application/execution_limits.py").read_text()

    assert "allowed_modes" in text
    assert "allowed_cli_flags" in text
    assert "allow_argv_exposure" in text
    assert "CLI_AUTH_INJECTION_MODES" in text


def test_credential_lease_service_is_documented_as_secret_resolution_boundary() -> None:
    service_text = Path("src/api/application/credential_leases.py").read_text()
    doc_text = Path("docs/architecture/credential-ref-boundary.md").read_text()
    runner_policy = Path("src/api/infrastructure/runners/AGENTS.md").read_text()

    assert "class CredentialLeaseService" in service_text
    assert "resolve_secret_for_runner" in service_text
    assert "CredentialLeaseService" in doc_text
    assert "CredentialLeaseService" in runner_policy
    assert "stores directly" in doc_text


def test_runner_side_materialization_contract_is_documented_and_redacted() -> None:
    service_text = Path("src/api/infrastructure/credentials/materialization.py").read_text()
    doc_text = Path("docs/architecture/credential-ref-boundary.md").read_text()
    runner_policy = Path("src/api/infrastructure/runners/AGENTS.md").read_text()

    assert "class CredentialMaterializationPlan" in service_text
    assert "redacted_command_for_log" in service_text
    assert "CredentialMaterializationPlan" in doc_text
    assert "CredentialMaterializationPlan" in runner_policy
    assert "temp-file descriptors" in doc_text
    assert "redacted command view" in doc_text


def test_command_invocation_env_overlay_boundary_is_documented() -> None:
    boundary_text = Path("src/api/infrastructure/commands/command_boundary.py").read_text()
    executor_text = Path("src/api/infrastructure/commands/command_executor.py").read_text()
    doc_text = Path("docs/architecture/credential-ref-boundary.md").read_text()
    runner_policy = Path("src/api/infrastructure/runners/AGENTS.md").read_text()

    assert "env: Mapping" in boundary_text
    assert "redact_command_env" in boundary_text
    assert "summarize_env_for_log" in boundary_text
    assert "process_env = self.invocation.process_env(os.environ)" in executor_text
    assert "env overlay" in doc_text
    assert "logs only env names" in runner_policy


def test_secret_version_lifecycle_boundary_is_documented() -> None:
    service_text = Path("src/api/application/credential_secret_versions.py").read_text()
    storage_text = Path("src/api/application/credential_storage.py").read_text()
    doc_text = Path("docs/architecture/credential-ref-boundary.md").read_text()
    handoff_text = Path("HANDOFF_FOR_NEW_CHAT.md").read_text()

    assert "class CredentialSecretVersionService" in service_text
    assert "rotate_secret" in service_text
    assert "mark_current_secret_expired" in service_text
    assert "current_secret_version_id" in storage_text
    assert "refresh_status" in storage_text
    assert "replaced_by_version_id" in storage_text
    assert "Secret Version Lifecycle" in doc_text
    assert "current active, unexpired secret version" in doc_text
    assert "CredentialSecretVersionService" in handoff_text


def test_postgres_credential_store_and_secret_codec_boundary_are_documented() -> None:
    store_text = Path("src/api/infrastructure/credential_store.py").read_text()
    codec_text = Path("src/api/infrastructure/credentials/secret_codec.py").read_text()
    doc_text = Path("docs/architecture/credential-ref-boundary.md").read_text()
    handoff_text = Path("HANDOFF_FOR_NEW_CHAT.md").read_text()

    assert "class PostgresCredentialStore" in store_text
    assert "secret_codec" in store_text
    assert "class SecretCodec" in codec_text
    assert "DevOnlyPlaintextSecretCodec" in codec_text
    assert "LocalEncryptedSecretCodec" in codec_text
    assert "AES-256-GCM" in codec_text
    assert "PostgresCredentialStore" in doc_text
    assert "SecretCodec" in doc_text
    assert "LocalEncryptedSecretCodec" in doc_text
    assert "CREDENTIAL_MASTER_KEY" in doc_text
    assert "DevOnlyPlaintextSecretCodec" in handoff_text
    assert "LocalEncryptedSecretCodec" in handoff_text


def test_credential_backend_composition_boundary_is_documented_and_configured() -> None:
    settings_text = Path("src/api/config.py").read_text()
    factory_text = Path("src/api/infrastructure/credentials/factory.py").read_text()
    doc_text = Path("docs/architecture/credential-ref-boundary.md").read_text()
    handoff_text = Path("HANDOFF_FOR_NEW_CHAT.md").read_text()
    runner_policy = Path("src/api/infrastructure/runners/AGENTS.md").read_text()

    assert "CREDENTIAL_SECRET_BACKEND" in settings_text
    assert 'CREDENTIAL_SECRET_BACKEND: str = "postgres_encrypted"' in settings_text
    assert "CREDENTIAL_MASTER_KEY" in settings_text
    assert "CREDENTIAL_ALLOW_DEV_PLAINTEXT: bool = False" in settings_text
    assert "build_credential_secret_codec" in factory_text
    assert "build_postgres_credential_store" in factory_text
    assert "CREDENTIAL_ALLOW_DEV_PLAINTEXT=true" in doc_text
    assert "missing `CREDENTIAL_MASTER_KEY` fails closed" in handoff_text
    assert "Runners must not construct credential stores" in runner_policy


def test_credential_management_api_boundary_is_documented_and_registered() -> None:
    service_text = Path("src/api/application/credential_management.py").read_text()
    route_text = Path("src/api/presentation/rest/routes/credentials.py").read_text()
    router_text = Path("src/api/presentation/rest/routes/__init__.py").read_text()
    di_text = Path("src/api/application/di.py").read_text()
    doc_text = Path("docs/architecture/credential-ref-boundary.md").read_text()
    handoff_text = Path("HANDOFF_FOR_NEW_CHAT.md").read_text()

    assert "class CredentialManagementService" in service_text
    assert "SecretStr" in service_text
    assert "rotate_secret" in service_text
    assert "mark_current_secret_expired" in service_text
    assert "list_metadata" in service_text
    assert "resolve_secret_for_runner" not in service_text
    assert "resolve_secret_for_lease" not in service_text
    assert "materialize_credential_for_runner" not in route_text
    assert "credentials_router" in router_text
    assert 'prefix="/api/v1/credentials"' in router_text
    assert "class CredentialProvider" in di_text
    assert "build_postgres_credential_store" in di_text
    assert "CredentialManagementService" in doc_text
    assert "/api/v1/credentials" in doc_text
    assert "CredentialManagementService" in handoff_text
