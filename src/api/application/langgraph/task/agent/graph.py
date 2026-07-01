"""LangGraph wrapper for deterministic agent-task role dispatch."""
from __future__ import annotations

from typing import Any

from api.application.agent_task_runtime_contracts import AgentTaskRuntimeRequest
from api.application.langgraph.task.agent.helpers import safe_checkpoint_namespace
from api.application.langgraph.task.agent.models import (
    AgentTaskGraphState,
    agent_task_thread_ref,
)
from api.application.langgraph.task.agent.result import graph_state_from_role_reply, input_state
from api.application.agent.task.role import AgentTaskRoleComposer, normalize_agent_role


class LangGraphAgentTaskGraphRunner:
    """Minimal LangGraph boundary around a deterministic role composer.

    This graph is not a tool-capable reasoning loop. It only gives agent-task
    replies a LangGraph thread/checkpoint boundary while keeping role selection
    explicit and deterministic.
    """

    def __init__(
        self,
        *,
        role_composer: AgentTaskRoleComposer | None = None,
        checkpointer: Any | None = None,
        checkpoint_ns: str = "agent-task",
    ) -> None:
        try:
            from langgraph.graph import END, START, StateGraph
        except ModuleNotFoundError as exc:  # pragma: no cover - environment dependent
            raise RuntimeError(
                "LangGraphAgentTaskGraphRunner requires the langgraph package. "
                "Use AGENT_TASK_RUNTIME=bounded until dependencies are installed."
            ) from exc

        self._role_composer = role_composer or AgentTaskRoleComposer()
        self._checkpoint_ns = safe_checkpoint_namespace(checkpoint_ns)
        builder = StateGraph(AgentTaskGraphState)
        builder.add_node("guard_boundary", self._guard_boundary)
        builder.add_node("compose_role_reply", self._compose_role_reply)
        builder.add_edge(START, "guard_boundary")
        builder.add_edge("guard_boundary", "compose_role_reply")
        builder.add_edge("compose_role_reply", END)
        self._compiled = builder.compile(checkpointer=checkpointer) if checkpointer is not None else builder.compile()

    async def ainvoke(
        self,
        *,
        request: AgentTaskRuntimeRequest,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        thread_ref = agent_task_thread_ref(
            request.task_id,
            checkpoint_ns=self._checkpoint_ns,
        )
        state = input_state(request, context)
        state["langgraph_thread_id"] = thread_ref.thread_id
        state["langgraph_checkpoint_ns"] = thread_ref.checkpoint_ns
        result = await self._compiled.ainvoke(state, config=thread_ref.config())
        return dict(result or {})

    async def _guard_boundary(self, state: AgentTaskGraphState) -> AgentTaskGraphState:
        role = normalize_agent_role(str(state.get("target_agent") or "coordinator"))
        return {
            "agent_route": role,
            "boundary": {
                "tool_execution": "forbidden_from_langgraph_agent_task_runtime",
                "raw_artifact_access": "forbidden",
                "next_step": "agent_may_reply_or_propose_bounded_action_request",
            },
            "metadata": {
                "runtime": "langgraph-agent-task-runtime.v3",
                "graph": "agent-task-deterministic-role-dispatch.v1",
                "graph_kind": "deterministic_role_dispatch",
                "source_message_id": state.get("message_id"),
                "selected_agent_role": role,
                "langgraph_thread": {
                    "thread_id": state.get("langgraph_thread_id"),
                    "checkpoint_ns": state.get("langgraph_checkpoint_ns"),
                    "owner": "langgraph",
                    "domain_task_id": state.get("task_id"),
                },
            },
        }

    async def _compose_role_reply(self, state: AgentTaskGraphState) -> AgentTaskGraphState:
        role = normalize_agent_role(str(state.get("agent_route") or state.get("target_agent") or "coordinator"))
        reply = self._role_composer.compose(
            target_agent=role,
            body_excerpt=str(state.get("body_excerpt") or ""),
            context=dict(state.get("context") or {}),
        )
        return graph_state_from_role_reply(state, reply)
