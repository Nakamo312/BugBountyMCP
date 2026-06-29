from __future__ import annotations

from pathlib import Path

from sqlalchemy import CheckConstraint, UniqueConstraint

from api.infrastructure.adapters.orm import metadata


CREDENTIAL_STORAGE_TABLES = {
    "credential_refs",
    "credential_secret_versions",
    "credential_leases",
}


def _constraint_names(table_name: str, constraint_type: type) -> set[str]:
    table = metadata.tables[table_name]
    return {
        constraint.name
        for constraint in table.constraints
        if isinstance(constraint, constraint_type) and constraint.name is not None
    }


def _index_names(table_name: str) -> set[str]:
    table = metadata.tables[table_name]
    return {index.name for index in table.indexes if index.name is not None}


def test_credential_storage_tables_are_declared_in_orm_metadata() -> None:
    assert CREDENTIAL_STORAGE_TABLES <= set(metadata.tables)

    refs = metadata.tables["credential_refs"]
    secret_versions = metadata.tables["credential_secret_versions"]
    leases = metadata.tables["credential_leases"]

    for column in (
        "program_id",
        "credential_ref",
        "identity_label",
        "secret_kind",
        "scope_json",
        "status",
        "expires_at",
        "current_secret_version_id",
        "refresh_policy_json",
        "refresh_status",
        "last_refreshed_at",
        "next_refresh_at",
        "metadata_json",
    ):
        assert column in refs.c
    assert "uq_credential_refs_program_ref" in _constraint_names("credential_refs", UniqueConstraint)
    assert "idx_credential_refs_program_status" in _index_names("credential_refs")
    assert "idx_credential_refs_program_refresh" in _index_names("credential_refs")
    assert "ck_credential_refs_refresh_status_valid" in _constraint_names(
        "credential_refs",
        CheckConstraint,
    )

    for column in (
        "credential_ref_id",
        "version",
        "secret_kind",
        "storage_backend",
        "ciphertext",
        "nonce",
        "key_id",
        "external_secret_ref",
        "status",
        "expires_at",
        "replaced_by_version_id",
    ):
        assert column in secret_versions.c
    assert "uq_credential_secret_versions_ref_version" in _constraint_names(
        "credential_secret_versions",
        UniqueConstraint,
    )
    assert "ck_credential_secret_versions_has_secret_pointer" in _constraint_names(
        "credential_secret_versions",
        CheckConstraint,
    )
    assert "ck_credential_secret_versions_not_self_replaced" in _constraint_names(
        "credential_secret_versions",
        CheckConstraint,
    )

    for column in (
        "program_id",
        "credential_ref_id",
        "secret_version_id",
        "purpose",
        "capability",
        "target_scope",
        "auth_injection_json",
        "status",
        "issued_at",
        "expires_at",
        "audit_json",
    ):
        assert column in leases.c
    assert "idx_credential_leases_program_status_expires" in _index_names("credential_leases")
    assert "ck_credential_leases_expires_after_issued" in _constraint_names(
        "credential_leases",
        CheckConstraint,
    )


def test_credential_storage_migration_follows_current_search_projection_head() -> None:
    migration = Path("alembic/versions/e8f9a0b1c2d3_add_credential_secret_storage.py")
    source = migration.read_text(encoding="utf-8")

    assert 'down_revision: Union[str, None] = "d7e8f9a0b1c2"' in source
    for table_name in CREDENTIAL_STORAGE_TABLES:
        assert f'"{table_name}"' in source
    assert "ciphertext" in source
    assert "external_secret_ref" in source
    assert "credential_ref LIKE 'credref:%'" in source


def test_credential_secret_lifecycle_migration_follows_storage_foundation() -> None:
    migration = Path("alembic/versions/f9a0b1c2d3e4_credential_secret_version_lifecycle.py")
    source = migration.read_text(encoding="utf-8")

    assert 'down_revision: Union[str, None] = "e8f9a0b1c2d3"' in source
    assert "current_secret_version_id" in source
    assert "refresh_policy_json" in source
    assert "refresh_status" in source
    assert "replaced_by_version_id" in source
    assert "status IN ('active', 'retired', 'expired', 'revoked')" in source
