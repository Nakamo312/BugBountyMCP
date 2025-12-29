import pytest

from api.infrastructure.normalization.path_normalizer import PathNormalizer


@pytest.fixture
def normalizer():
    return PathNormalizer()


def test_normalizes_numeric_ids(normalizer):
    """Test that numeric IDs are replaced with {id}"""
    assert normalizer.normalize_path("/api/users/123") == "/api/users/{id}"
    assert normalizer.normalize_path("/api/users/456/posts/789") == "/api/users/{id}/posts/{id}"


def test_normalizes_uuids(normalizer):
    """Test that UUIDs are replaced with {uuid}"""
    path = "/api/users/550e8400-e29b-41d4-a716-446655440000"
    assert normalizer.normalize_path(path) == "/api/users/{uuid}"


def test_normalizes_sha256_hashes(normalizer):
    """Test that SHA256 hashes are replaced with {sha256}"""
    path = "/files/e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    normalized = normalizer.normalize_path(path)
    assert "{sha256}" in normalized


def test_preserves_static_segments(normalizer):
    """Test that non-ID segments are preserved"""
    assert normalizer.normalize_path("/api/v1/users") == "/api/v1/users"
    assert normalizer.normalize_path("/api/v2/posts/search") == "/api/v2/posts/search"


def test_deduplicates_similar_paths(normalizer):
    """Test that similar paths normalize to same value"""
    paths = [
        "/api/users/123",
        "/api/users/456",
        "/api/users/789"
    ]
    normalized = {normalizer.normalize_path(p) for p in paths}
    assert len(normalized) == 1
    assert "/api/users/{id}" in normalized


def test_handles_trailing_slash(normalizer):
    """Test that trailing slashes are normalized"""
    with_slash = normalizer.normalize_path("/api/users/")
    without_slash = normalizer.normalize_path("/api/users")
    assert with_slash == without_slash


def test_handles_root_path(normalizer):
    """Test root path normalization"""
    assert normalizer.normalize_path("/") == "/"
    assert normalizer.normalize_path("") == "/"


def test_handles_complex_nested_paths(normalizer):
    """Test complex nested paths with multiple IDs"""
    path = "/api/v2/organizations/123/projects/456/tasks/789/comments/012"
    normalized = normalizer.normalize_path(path)
    assert normalized == "/api/v2/organizations/{id}/projects/{id}/tasks/{id}/comments/{id}"
