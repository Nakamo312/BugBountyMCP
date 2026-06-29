from __future__ import annotations

import importlib


def test_split_application_modules_import_cleanly() -> None:
    proposals = importlib.import_module("api.application.action_experience_proposals")
    acceptance = importlib.import_module("api.application.action_experience_acceptance")

    assert proposals.ActionExperienceProposalAcceptanceService is acceptance.ActionExperienceProposalAcceptanceService


def test_split_graph_projector_modules_import_cleanly() -> None:
    importlib.import_module("graph_projector.action_experience_proposals")
    importlib.import_module("graph_projector.proposal_store_statements")
    importlib.import_module("graph_projector.proposal_upsert_statements")


def test_split_contract_modules_import_cleanly() -> None:
    contracts = importlib.import_module("api.application.contracts")
    enums = importlib.import_module("api.application.contract_enums")
    action = importlib.import_module("api.application.action_contracts")
    outcomes = importlib.import_module("api.application.action_outcome_contracts")
    events = importlib.import_module("api.application.event_contracts")
    invocations = importlib.import_module("api.application.invocation_contracts")
    pipeline = importlib.import_module("api.application.pipeline_contracts")

    assert contracts.ActionRequest is action.ActionRequest
    assert contracts.ActionOutcomeRecord is outcomes.ActionOutcomeRecord
    assert contracts.EventEnvelope is events.EventEnvelope
    assert contracts.ToolInvocation is invocations.ToolInvocation
    assert contracts.NodeRunClaim is pipeline.NodeRunClaim
    assert contracts.ActionStatus is enums.ActionStatus


def test_split_agent_task_langgraph_modules_import_cleanly() -> None:
    facade = importlib.import_module("api.application.agent_task_langgraph_runtime")
    models = importlib.import_module("api.application.agent_task_langgraph_models")
    context = importlib.import_module("api.application.agent_task_langgraph_context")
    factory = importlib.import_module("api.application.agent_task_langgraph_factory")
    graph = importlib.import_module("api.application.agent_task_langgraph_graph")
    result = importlib.import_module("api.application.agent_task_langgraph_result")

    assert facade.AgentTaskRuntimeFactory is factory.AgentTaskRuntimeFactory
    assert facade.LangGraphAgentTaskRuntime is factory.LangGraphAgentTaskRuntime
    assert facade.LangGraphAgentTaskGraphRunner is graph.LangGraphAgentTaskGraphRunner
    assert facade.EmptyAgentTaskContextReader is context.EmptyAgentTaskContextReader
    assert facade.AgentTaskGraphState is models.AgentTaskGraphState
    assert facade._runtime_result_from_graph_state is result.runtime_result_from_graph_state
