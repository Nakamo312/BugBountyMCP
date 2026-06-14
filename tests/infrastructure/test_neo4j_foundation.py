from pathlib import Path

import yaml


def test_graph_projector_settings_parse_url_user_password(monkeypatch) -> None:
    import sys

    sys.path.insert(0, str(Path("services/graph-projector").resolve()))
    from graph_projector.settings import GraphProjectorSettings

    monkeypatch.setenv("NEO4J_ENABLED", "true")
    monkeypatch.setenv("NEO4J_URI", "bolt://neo4j:7687")
    monkeypatch.setenv("NEO4J_USER", "graph-user")
    monkeypatch.setenv("NEO4J_PASSWORD", "graph-password")
    monkeypatch.setenv("NEO4J_DATABASE", "graph-db")

    settings = GraphProjectorSettings.from_env()

    assert settings.neo4j_enabled is True
    assert settings.neo4j_uri == "bolt://neo4j:7687"
    assert settings.neo4j_user == "graph-user"
    assert settings.neo4j_password == "graph-password"
    assert settings.neo4j_database == "graph-db"


def test_disabled_graph_projector_driver_does_not_require_driver_package() -> None:
    import sys

    sys.path.insert(0, str(Path("services/graph-projector").resolve()))
    from graph_projector.neo4j_driver import create_neo4j_driver
    from graph_projector.settings import GraphProjectorSettings

    settings = GraphProjectorSettings(neo4j_enabled=False)

    assert create_neo4j_driver(settings) is None


def test_api_service_does_not_import_neo4j_driver() -> None:
    assert not Path("src/api/infrastructure/graph/neo4j_driver.py").exists()


def test_docker_compose_graph_projector_is_optional_graph_profile() -> None:
    compose = yaml.safe_load(Path("docker-compose.yml").read_text(encoding="utf-8"))
    services = compose["services"]

    assert services["neo4j"]["profiles"] == ["graph"]
    assert services["graph-projector"]["profiles"] == ["graph"]
    assert services["graph-projector"]["depends_on"]["neo4j"]["condition"] == "service_healthy"
    assert "neo4j_data" in compose["volumes"]
