"""Runtime and factory wiring for the LangGraph-backed agent task runtime."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from api.application.agent_task_runtime_contracts import (
    AgentTaskRuntime,
    AgentTaskRuntimeRequest,
    AgentTaskRuntimeResult,
    BoundedAgentTaskRuntime,
)
from api.application.langgraph.task.agent.context import EmptyAgentTaskContextReader
from api.application.langgraph.task.agent.graph import LangGraphAgentTaskGraphRunner
from api.application.langgraph.task.agent.models import (
    AgentTaskContextReader,
    AgentTaskGraphRunner,
    agent_task_thread_ref,
)
from api.application.langgraph.task.agent.result import runtime_result_from_graph_state


@dataclass(frozen=True, slots=True)
class LangGraphAgentTaskRuntime:
    """AgentTaskRuntime implementation backed by a LangGraph runner."""

    runner: AgentTaskGraphRunner = field(default_factory=lambda: LangGraphAgentTaskGraphRunner())
    context_reader: AgentTaskContextReader = field(default_factory=EmptyAgentTaskContextReader)
    checkpoint_ns: str = "agent-task"

    async def handle(self, request: AgentTaskRuntimeRequest) -> AgentTaskRuntimeResult:
        context = await self.context_reader.read(request)
        thread_ref = agent_task_thread_ref(
            request.task_id,
            checkpoint_ns=self.checkpoint_ns,
        )
        context = {
            **context,
            "langgraph_thread": thread_ref.to_metadata(),
        }
        graph_state = await self.runner.ainvoke(request=request, context=context)
        return runtime_result_from_graph_state(
            request=request,
            graph_state=graph_state,
            context=context,
            thread_ref=thread_ref,
        )


@dataclass(frozen=True, slots=True)
class AgentTaskRuntimeFactory:
    """Factory used by DI to select bounded or LangGraph task runtime."""

    runtime_name: str = "bounded"
    default_budget_mode: str = "none"
    allow_deep_budget_mode: bool = False
    require_deep_confirmation: bool = True
    deep_allowed_actors: str = "human,operator,admin"
    context_reader: AgentTaskContextReader | None = None
    langgraph_checkpointer: Any | None = None
    langgraph_checkpoint_ns: str = "agent-task"

    def create(self) -> AgentTaskRuntime:
        from api.application.agent_task_budget import (
            AgentTaskRuntimeBudgetPolicy,
            BudgetedAgentTaskRuntime,
        )

        name = (self.runtime_name or "bounded").strip().lower().replace("_", "-")
        fallback = BoundedAgentTaskRuntime()
        if name in {"bounded", "safe", "fallback"}:
            inner: AgentTaskRuntime = fallback
        elif name in {"langgraph", "langgraph-local"}:
            inner = LangGraphAgentTaskRuntime(
                runner=LangGraphAgentTaskGraphRunner(
                    checkpointer=self.langgraph_checkpointer,
                    checkpoint_ns=self.langgraph_checkpoint_ns,
                ),
                context_reader=self.context_reader or EmptyAgentTaskContextReader(),
                checkpoint_ns=self.langgraph_checkpoint_ns,
            )
        else:
            raise ValueError("AGENT_TASK_RUNTIME must be one of: bounded, langgraph")
        return BudgetedAgentTaskRuntime(
            inner=inner,
            fallback=fallback,
            policy=AgentTaskRuntimeBudgetPolicy(
                default_mode=self.default_budget_mode,
                allow_deep=self.allow_deep_budget_mode,
                require_deep_confirmation=self.require_deep_confirmation,
                deep_allowed_actors=self.deep_allowed_actors,
            ),
        )
