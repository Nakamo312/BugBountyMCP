"""Compatibility façade for the LangGraph-backed agent task runtime.

The runtime still routes visible agent replies through a bounded LangGraph
runner/thread_id boundary and stamps the result with forbidden_from_langgraph_agent_task_runtime.
No tool dispatcher or execution surface is imported here.
"""
from __future__ import annotations

from api.application.agent_task_langgraph_context import EmptyAgentTaskContextReader
from api.application.agent_task_langgraph_factory import (
    AgentTaskRuntimeFactory,
    LangGraphAgentTaskRuntime,
)
from api.application.agent_task_langgraph_graph import LangGraphAgentTaskGraphRunner
from api.application.agent_task_langgraph_helpers import (
    agent_key as _agent_key,
    bounded_dicts as _bounded_dicts,
    bounded_mapping as _bounded_mapping,
    optional_text as _optional_text,
    optional_uuid_text as _optional_uuid_text,
    safe_checkpoint_namespace as _safe_checkpoint_namespace,
)
from api.application.agent_task_langgraph_models import (
    AgentTaskContextReader,
    AgentTaskGraphRunner,
    AgentTaskGraphState,
    AgentTaskLangGraphThreadRef,
    agent_task_langgraph_thread_ref,
)
from api.application.agent_task_langgraph_result import (
    graph_state_from_role_reply as _graph_state_from_role_reply,
    input_state as _input_state,
    message_kind as _message_kind,
    proposal_drafts as _proposal_drafts,
    reply_body as _reply_body,
    runtime_result_from_graph_state as _runtime_result_from_graph_state,
    safe_context as _safe_context,
    status as _status,
)

__all__ = [
    "AgentTaskContextReader",
    "AgentTaskGraphRunner",
    "AgentTaskGraphState",
    "AgentTaskLangGraphThreadRef",
    "AgentTaskRuntimeFactory",
    "EmptyAgentTaskContextReader",
    "LangGraphAgentTaskGraphRunner",
    "LangGraphAgentTaskRuntime",
    "agent_task_langgraph_thread_ref",
]
