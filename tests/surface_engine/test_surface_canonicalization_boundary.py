import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SURFACE_ROOT = ROOT / "services" / "surface-engine"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(SURFACE_ROOT))

from surface_engine import (  # noqa: E402
    CanonicalizationAliases,
    EndpointObservationInput,
    RequestShapeInput,
    ResponseShapeInput,
    TransportObservationInput,
    canonicalize_endpoint,
    canonicalize_observation,
)


def test_structured_canonicalization_matches_legacy_flat_wrapper() -> None:
    structured = canonicalize_observation(
        EndpointObservationInput(
            program_id="program-1",
            url="https://example.com:443/api/users/123?token=raw",
            method="post",
            transport=TransportObservationInput(
                scheme="https",
                port=443,
                http_version="h2",
                alpn="h2",
            ),
            request_shape=RequestShapeInput(
                content_type="application/json",
                body_field_value_types={"email": "string"},
                json_keys=["email"],
            ),
            response_shape=ResponseShapeInput(
                status_code=201,
                header_names=["Content-Type"],
                content_type="application/json; charset=utf-8",
                json_keys=["id", "email"],
                body_sha256="a" * 64,
            ),
        )
    )

    legacy = canonicalize_endpoint(
        program_id="program-1",
        url="https://example.com:443/api/users/123?token=raw",
        method="post",
        scheme="https",
        port=443,
        http_version="h2",
        alpn="h2",
        request_content_type="application/json",
        request_body_field_value_types={"email": "string"},
        request_json_keys=["email"],
        status_code=201,
        header_names=["Content-Type"],
        response_content_type="application/json; charset=utf-8",
        response_json_keys=["id", "email"],
        response_body_sha256="a" * 64,
    )

    assert structured.to_features() == legacy.to_features()


def test_legacy_aliases_are_isolated_from_normal_response_shape() -> None:
    endpoint = canonicalize_observation(
        EndpointObservationInput(
            url="https://example.com/api/users/123",
            response_shape=ResponseShapeInput(status_code=200),
            aliases=CanonicalizationAliases(
                content_type="application/json",
                json_keys=["legacy_id"],
                body_sha256="b" * 64,
            ),
        )
    )

    assert endpoint.response_body_shape is not None
    assert endpoint.response_body_shape.content_type == "application/json"
    assert endpoint.response_body_shape.json_keys == ["legacy_id"]
    assert endpoint.response_body_shape.content_family_fingerprint == "b" * 64


def test_surface_engine_internal_callers_use_structured_input() -> None:
    for relative_path in [
        "services/surface-engine/surface_engine/nodes/observation.py",
        "services/surface-engine/surface_engine/cli.py",
    ]:
        source = (ROOT / relative_path).read_text()
        assert "canonicalize_observation" in source
        assert "canonicalize_endpoint(" not in source


def test_legacy_flat_canonicalize_endpoint_is_only_a_wrapper() -> None:
    wrapper_source = inspect.getsource(canonicalize_endpoint)
    module_source = (ROOT / "services/surface-engine/surface_engine/canonicalization/legacy.py").read_text()

    assert "def canonicalize_endpoint(**kwargs: Any)" in wrapper_source
    assert "canonicalize_observation(_legacy_observation_input(kwargs))" in wrapper_source
    assert "EndpointObservationInput(" in module_source
    assert "TransportObservationInput(" in module_source
    assert "RequestShapeInput(" in module_source
    assert "ResponseShapeInput(" in module_source
    assert "CanonicalizationAliases(" in module_source
    assert "urlparse(" not in module_source
    assert "build_feature_fingerprint(" not in module_source


def test_canonicalize_observation_stays_thin_orchestrator() -> None:
    source = (ROOT / "services/surface-engine/surface_engine/canonicalization/endpoint.py").read_text()

    assert "PathNormalizer" not in source
    assert "re.compile" not in source
    assert "def normalize_route_template" not in source
    assert "def build_body_shape" not in source
    assert "def normalize_http_version" not in source
    assert "def normalize_query_value_types" not in source
    assert "build_route_material" in source
    assert "build_query_material" in source
    assert "build_request_material" in source
    assert "build_response_material" in source
    assert "build_transport_shape" in source


def test_canonicalization_materials_are_split_by_responsibility() -> None:
    expected_modules = [
        "route.py",
        "body.py",
        "materials.py",
        "transport.py",
        "inputs.py",
        "models.py",
        "legacy.py",
        "endpoint.py",
    ]
    for module_name in expected_modules:
        assert (ROOT / "services/surface-engine/surface_engine/canonicalization" / module_name).exists()

    route_source = (ROOT / "services/surface-engine/surface_engine/canonicalization/route.py").read_text()
    body_source = (ROOT / "services/surface-engine/surface_engine/canonicalization/body.py").read_text()
    material_source = (ROOT / "services/surface-engine/surface_engine/canonicalization/materials.py").read_text()
    transport_source = (ROOT / "services/surface-engine/surface_engine/canonicalization/transport.py").read_text()

    assert "normalize_route_template" in route_source
    assert "build_body_shape" in body_source
    assert "build_query_material" in material_source
    assert "build_transport_shape" in transport_source
    assert "build_feature_fingerprint" not in route_source
    assert "build_feature_fingerprint" not in body_source
    assert "build_feature_fingerprint" not in material_source
    assert "build_feature_fingerprint" not in transport_source


def test_flat_canonicalization_modules_stay_removed() -> None:
    old_modules = [
        "canonical_body.py",
        "canonical_inputs.py",
        "canonical_legacy.py",
        "canonical_materials.py",
        "canonical_models.py",
        "canonical_route.py",
        "canonical_transport.py",
        "canonicalize.py",
    ]
    for module_name in old_modules:
        assert not (ROOT / "services/surface-engine/surface_engine" / module_name).exists()

    assert (ROOT / "services/surface-engine/surface_engine/canonicalization").is_dir()
