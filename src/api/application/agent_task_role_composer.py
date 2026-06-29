"""Role-specific agent task reply composer."""
from __future__ import annotations

from typing import Any

from api.application.agent_tasks import AgentTaskMessageKind, AgentTaskStatus
from api.application.agent_task_role_context import ContextRefSummary
from api.application.agent_task_role_models import AgentTaskRoleReply
from api.application.agent_task_role_proposals import (
    _proposal_context_refs,
    _proposal_draft,
    _role_metadata,
)
from api.application.agent_task_role_text import (
    _artifact_focus,
    _artifact_next_step,
    _artifact_proposal_title,
    _coordinator_expected_gain,
    _coordinator_next_step,
    _coordinator_priority,
    _coordinator_proposal_title,
    _critic_next_step,
    _critic_proposal_title,
    _critic_risk_brief,
    _has_stop_signal,
    _has_surface_signal,
    _join_sections,
    _pending_proposal_brief,
    _recent_http_brief,
    _recent_javascript_brief,
    _recent_outcome_brief,
    _report_readiness_brief,
    _request_line,
    _surface_focus,
    _surface_next_step,
    _surface_proposal_title,
    normalize_agent_role,
)


class AgentTaskRoleComposer:
    """Compose visible replies for agent roles from bounded context only."""

    def compose(
        self,
        *,
        target_agent: str,
        body_excerpt: str,
        context: dict[str, Any],
    ) -> AgentTaskRoleReply:
        role = normalize_agent_role(target_agent)
        if role == "surface":
            return self.surface(body_excerpt=body_excerpt, context=context)
        if role == "artifacts":
            return self.artifacts(body_excerpt=body_excerpt, context=context)
        if role == "critic":
            return self.critic(body_excerpt=body_excerpt, context=context)
        if role == "report":
            return self.report(body_excerpt=body_excerpt, context=context)
        return self.coordinator(body_excerpt=body_excerpt, context=context)

    def coordinator(self, *, body_excerpt: str, context: dict[str, Any]) -> AgentTaskRoleReply:
        summary = ContextRefSummary.from_context(context)
        next_step = _coordinator_next_step(summary)
        body = _join_sections(
            "Координатор собрал состояние задачи.",
            _request_line(body_excerpt),
            summary.human_line(),
            _recent_outcome_brief(summary),
            _pending_proposal_brief(summary),
            next_step,
            "Если понадобится запуск инструмента, верну proposal. Сам агент действие не выполняет.",
        )
        return AgentTaskRoleReply(
            agent_key="coordinator",
            body=body,
            message_kind=AgentTaskMessageKind.PROPOSAL,
            status=AgentTaskStatus.WAITING,
            proposal_drafts=(
                _proposal_draft(
                    title=_coordinator_proposal_title(summary),
                    summary="Координатор предлагает следующий bounded исследовательский шаг на основе compact context, outcomes и pending proposals.",
                    rationale=next_step,
                    priority=_coordinator_priority(summary),
                    expected_gain=_coordinator_expected_gain(summary),
                    action_intent="coordinate_next_investigation_step",
                    context_refs=_proposal_context_refs(summary),
                ),
            ),
            metadata=_role_metadata("coordinator", summary),
        )

    def surface(self, *, body_excerpt: str, context: dict[str, Any]) -> AgentTaskRoleReply:
        summary = ContextRefSummary.from_context(context)
        body = _join_sections(
            "Агент поверхности разобрал компактный surface context.",
            _request_line(body_excerpt),
            summary.human_line(),
            _surface_focus(summary),
            _recent_http_brief(summary),
            _surface_next_step(summary),
            "Инструменты из сообщения не запускаю. Возвращаю только сжатые выводы и refs.",
        )
        return AgentTaskRoleReply(
            agent_key="surface",
            body=body,
            message_kind=AgentTaskMessageKind.FINDING,
            status=AgentTaskStatus.WAITING,
            graph_refs=tuple(summary.refs_by_kind.get("graph", ())[:5]),
            fact_refs=tuple(summary.refs_by_kind.get("surface", ())[:5]),
            proposal_drafts=(
                _proposal_draft(
                    title=_surface_proposal_title(summary),
                    summary="Агент поверхности предлагает выделить ветки, endpoints и response-shape изменения из compact surface context.",
                    rationale=_surface_next_step(summary),
                    priority="high" if _has_surface_signal(summary) else "medium",
                    expected_gain="Сузить внимание до веток, где поверхность реально изменилась или требует ручного решения.",
                    action_intent="review_surface_delta",
                    context_refs=_proposal_context_refs(summary),
                ),
            ),
            metadata=_role_metadata("surface", summary),
        )

    def artifacts(self, *, body_excerpt: str, context: dict[str, Any]) -> AgentTaskRoleReply:
        summary = ContextRefSummary.from_context(context)
        body = _join_sections(
            "Агент артефактов разобрал compact artifact/surface refs.",
            _request_line(body_excerpt),
            summary.human_line(),
            _artifact_focus(summary),
            _recent_javascript_brief(summary),
            _artifact_next_step(summary),
            "Raw output не читаю и не пересылаю. В ответ попадают только сжатые находки и ссылки.",
        )
        return AgentTaskRoleReply(
            agent_key="artifacts",
            body=body,
            message_kind=AgentTaskMessageKind.FINDING,
            status=AgentTaskStatus.WAITING,
            artifact_refs=tuple(summary.refs_by_kind.get("artifact", ())[:8]),
            fact_refs=tuple(summary.refs_by_kind.get("fact", ())[:8]),
            proposal_drafts=(
                _proposal_draft(
                    title=_artifact_proposal_title(summary),
                    summary="Агент артефактов предлагает разобрать JS refs, HTTP observations, параметры, формы и parser gaps без доступа к raw output.",
                    rationale=_artifact_next_step(summary),
                    priority="high" if summary.surface_counts.get("javascript_references", 0) else "medium",
                    expected_gain="Найти новые пути и точки ввода из уже нормализованных refs.",
                    action_intent="review_artifact_findings",
                    context_refs=_proposal_context_refs(summary),
                ),
            ),
            metadata=_role_metadata("artifacts", summary),
        )

    def critic(self, *, body_excerpt: str, context: dict[str, Any]) -> AgentTaskRoleReply:
        summary = ContextRefSummary.from_context(context)
        body = _join_sections(
            "Критик проверил задачу на шум, повторы и риск.",
            _request_line(body_excerpt),
            summary.human_line(),
            _critic_risk_brief(summary),
            _critic_next_step(summary),
            "Не подтверждаю баги и не запускаю инструменты. Готовлю решение: продолжать, сузить, остановить или запросить evidence.",
        )
        return AgentTaskRoleReply(
            agent_key="critic",
            body=body,
            message_kind=AgentTaskMessageKind.QUESTION,
            status=AgentTaskStatus.WAITING,
            decision_refs=tuple(summary.refs_by_kind.get("decision", ())[:5]),
            proposal_drafts=(
                _proposal_draft(
                    title=_critic_proposal_title(summary),
                    summary="Критик предлагает перед запуском отсечь повторы, scope-risk и дорогие действия без ожидаемого прироста.",
                    rationale=_critic_next_step(summary),
                    priority="high" if _has_stop_signal(summary) else "medium",
                    risk_level="medium" if _has_stop_signal(summary) else "low",
                    expected_gain="Снизить расход бюджета и не плодить мусорные действия.",
                    action_intent="review_noise_and_scope_risk",
                    context_refs=_proposal_context_refs(summary),
                ),
            ),
            metadata=_role_metadata("critic", summary),
        )

    def report(self, *, body_excerpt: str, context: dict[str, Any]) -> AgentTaskRoleReply:
        summary = ContextRefSummary.from_context(context)
        body = _join_sections(
            "Агент отчёта проверил, хватает ли evidence context.",
            _request_line(body_excerpt),
            summary.human_line(),
            _report_readiness_brief(summary),
            "Черновик отчёта не создаю без evidence refs, воспроизводимости, scope proof и вывода критика.",
        )
        return AgentTaskRoleReply(
            agent_key="report",
            body=body,
            message_kind=AgentTaskMessageKind.QUESTION,
            status=AgentTaskStatus.WAITING,
            artifact_refs=tuple(summary.refs_by_kind.get("artifact", ())[:5]),
            fact_refs=tuple(summary.refs_by_kind.get("evidence", ())[:5]),
            metadata=_role_metadata("report", summary),
        )
