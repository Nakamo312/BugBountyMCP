from __future__ import annotations

from pathlib import Path

ROOT = Path(".")
RESEARCH_MODEL = ROOT / "docs/architecture/research-operating-model.md"
GRAPH_ROLE = ROOT / "docs/architecture/graph-math-role.md"
HANDOFF = ROOT / "HANDOFF_FOR_NEW_CHAT.md"
AGENTS = ROOT / "AGENTS.md"
README = ROOT / "README.md"
DOCS_INDEX = ROOT / "docs/README.md"

ARCHITECTURE_DOCS = (
    RESEARCH_MODEL,
    GRAPH_ROLE,
    HANDOFF,
    AGENTS,
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _flat(text: str) -> str:
    return " ".join(text.split())


def test_research_operating_model_is_documented_as_experience_first_substrate() -> None:
    text = _read(RESEARCH_MODEL)

    assert "experience-first security research system" in text
    assert "research substrate" in _flat(text)
    assert "state\n  -> hypothesis\n  -> approved action\n  -> observation" in text
    assert "PostgreSQL is canonical memory" in text
    assert "Every future patch must answer" in text


def test_rag_and_rlm_are_documented_as_distinct_non_execution_layers() -> None:
    text = _read(RESEARCH_MODEL)
    handoff = _read(HANDOFF)
    agents = _read(AGENTS)

    assert "RAG performs fast retrieval" in text
    assert "RLM is a deep recursive analysis path" in text
    assert "RLM does not execute tools and does not replace RAG" in _flat(text)
    assert "RAG and RLM" in agents
    assert "RAG и RLM не являются одним слоем" in handoff
    assert "Neither executes tools" in agents
    assert "Ни один из них не запускает tools" in _flat(handoff)


def test_graph_math_role_is_structural_signal_engine_not_bug_verdict_layer() -> None:
    text = _read(GRAPH_ROLE)
    model = _read(RESEARCH_MODEL)
    agents = _read(AGENTS)

    for document in (text, model, agents):
        assert "structural signal" in document

    assert "Graph math must not act as a bug oracle" in text
    assert "Graph math never calls a runner" in text
    assert "Graph math produces structural signals" in model
    assert "Neo4j/GDS produces structural signals, not findings" in _flat(agents)


def test_cli_tools_are_effectors_behind_action_service_boundary() -> None:
    text = _read(RESEARCH_MODEL)
    handoff = _read(HANDOFF)
    agents = _read(AGENTS)
    readme = _read(README)

    expected_flow = "ActionService -> policy -> scope -> approval -> budget -> CommandInvocation -> runner"

    assert "CLI tools are effectors" in text
    assert expected_flow in text
    assert expected_flow in handoff
    assert "CLI tools are effectors" in agents
    assert "ToolActionRequest\n  -> policy/scope/approval/budget" in readme


def test_vulnerability_labels_are_post_hoc_annotations_not_action_engine() -> None:
    text = _read(RESEARCH_MODEL)
    handoff = _read(HANDOFF)
    agents = _read(AGENTS)

    assert "post-hoc annotations" in text
    assert "must not become the primary action engine" in text
    assert "post-hoc annotations" in handoff
    assert "They do not become action engine" not in text
    assert "Do not treat vulnerability labels as the primary action engine" in agents


def test_docs_index_and_agent_index_link_new_architecture_baseline() -> None:
    for path in (AGENTS, DOCS_INDEX, README):
        text = _read(path)
        assert "docs/architecture/research-operating-model.md" in text or "architecture/research-operating-model.md" in text
        assert "docs/architecture/graph-math-role.md" in text or "architecture/graph-math-role.md" in text


def test_research_model_blocks_llm_shell_and_graph_to_action_shortcuts() -> None:
    text = _read(RESEARCH_MODEL)

    for forbidden_shortcut in (
        "LLM -> shell",
        "LLM -> RabbitMQ",
        "LLM -> runner",
        "LLM -> raw secret",
        "GDS result -> finding",
        "GDS result -> tool run",
        "vulnerability enum -> automatic action chain",
    ):
        assert forbidden_shortcut in text


def test_graph_projection_backlog_starts_from_typed_projection_inventory() -> None:
    text = _read(GRAPH_ROLE)
    handoff = _read(HANDOFF)

    expected_projection_names = {
        "G_asset",
        "G_http",
        "G_identity",
        "G_finding",
        "G_temporal",
        "G_bipartite_endpoint_param",
        "G_bipartite_host_tech",
        "G_bipartite_endpoint_object",
    }

    for projection_name in expected_projection_names:
        assert projection_name in text
        assert projection_name in handoff

    assert "A named projection is a mathematical space" in text
    assert "Each projection must define" in text
