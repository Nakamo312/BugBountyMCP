"""Text composition helpers for role-specific agent task replies."""
from __future__ import annotations

from typing import Any

from api.application.agent.task.role.context import ContextRefSummary, _safe_short


def normalize_agent_role(value: str) -> str:
    normalized = str(value or "").strip().lower().replace("_", "-").replace(" ", "-")
    aliases = {
        "coord": "coordinator",
        "coordinator": "coordinator",
        "координатор": "coordinator",
        "surface": "surface",
        "surface-agent": "surface",
        "agent-surface": "surface",
        "поверхность": "surface",
        "агент-поверхности": "surface",
        "artifact": "artifacts",
        "artifacts": "artifacts",
        "artifact-agent": "artifacts",
        "agent-artifacts": "artifacts",
        "артефакты": "artifacts",
        "агент-артефактов": "artifacts",
        "critic": "critic",
        "критик": "critic",
        "report": "report",
        "reporter": "report",
        "report-agent": "report",
        "отчет": "report",
        "отчёт": "report",
    }
    return aliases.get(normalized, "coordinator")


def _request_line(body_excerpt: str) -> str:
    text = str(body_excerpt or "").strip()
    if not text:
        return "Текст задачи пуст после санитарной обработки."
    return f"Кратко понял запрос: {text[:700]}"


def _surface_focus(summary: ContextRefSummary) -> str:
    if summary.surface_counts:
        endpoints = summary.surface_counts.get("endpoints", 0)
        http = summary.surface_counts.get("http_observations", 0)
        js = summary.surface_counts.get("javascript_references", 0)
        hosts = summary.surface_counts.get("hosts", 0)
        return f"Срез поверхности: hosts {hosts}, endpoints {endpoints}, HTTP observations {http}, JS refs {js}."
    if any(kind in summary.counts_by_kind for kind in ("surface", "endpoint", "graph")):
        return "Фокус: сравнить приложенные surface/graph refs и выделить изменение, а не пересказывать весь список URL."
    return "Фокус: сначала нужен surface context. Без него не буду делать выводы о новых ветках."


def _artifact_focus(summary: ContextRefSummary) -> str:
    js_refs = summary.surface_counts.get("javascript_references", 0)
    http_refs = summary.surface_counts.get("http_observations", 0)
    if js_refs or http_refs:
        return f"Срез артефактов: нормализованные HTTP observations {http_refs}, JS refs {js_refs}. Raw output в ленту не тащу."
    if any(kind in summary.counts_by_kind for kind in ("artifact", "fact", "js", "endpoint")):
        return "Фокус: извлечь из refs новые пути, параметры, JS-ссылки и parser gaps без чтения raw output в ленту."
    return "Фокус: сначала нужны artifact/fact refs. Без них не буду заявлять, что что-то найдено."


def _recent_outcome_brief(summary: ContextRefSummary) -> str:
    outcome = summary.strongest_outcome()
    if not outcome:
        return "Память исходов пока не дала сильного ориентира для этой задачи."
    counts = outcome.get("counts") if isinstance(outcome.get("counts"), dict) else {}
    gain = float(outcome.get("information_gain_score") or 0.0)
    capability = _safe_short(outcome.get("capability_id")) or "unknown-capability"
    profile = _safe_short(outcome.get("profile_id")) or "unknown-profile"
    pieces = [
        f"Лучший похожий недавний исход: {capability}/{profile}",
        f"gain {gain:.2f}",
    ]
    interesting_counts = _nonzero_count_line(counts, keys=("endpoints", "http_observations", "javascript_references", "raw_artifacts"))
    if interesting_counts:
        pieces.append(interesting_counts)
    feedback = outcome.get("human_feedback") if isinstance(outcome.get("human_feedback"), dict) else {}
    if feedback.get("continued_by_followup") or feedback.get("manual_interest"):
        pieces.append("human continued/interest")
    if feedback.get("manual_stop"):
        pieces.append("manual stop")
    return "; ".join(pieces) + "."


def _pending_proposal_brief(summary: ContextRefSummary) -> str:
    proposal = summary.top_pending_proposal()
    if not proposal:
        return "Pending experience proposals нет. Следующий шаг можно строить от текущего контекста и последних outcomes."
    capability = _safe_short(proposal.get("capability_id")) or "unknown-capability"
    profile = _safe_short(proposal.get("profile_id")) or "unknown-profile"
    utility = float(proposal.get("utility_score") or 0.0)
    samples = int(proposal.get("sample_count") or 0)
    return f"Сильнейший pending proposal из опыта: {capability}/{profile}, utility {utility:.2f}, samples {samples}."


def _recent_http_brief(summary: ContextRefSummary) -> str:
    if not summary.recent_http:
        return "Recent HTTP samples нет в compact context. Не буду выдумывать новые endpoints."
    lines: list[str] = []
    for item in summary.recent_http[:3]:
        method = _safe_short(item.get("method")) or "GET"
        url = _safe_short(item.get("url_excerpt"), limit=120) or "unknown-url"
        status = item.get("status_code")
        content_type = _safe_short(item.get("content_type"), limit=60)
        suffix = f" -> {status}" if status is not None else ""
        if content_type:
            suffix += f" {content_type}"
        lines.append(f"{method} {url}{suffix}")
    return "Последние HTTP наблюдения: " + "; ".join(lines) + "."


def _recent_javascript_brief(summary: ContextRefSummary) -> str:
    if not summary.recent_javascript:
        return "Recent JS refs нет в compact context. Не буду заявлять скрытые пути без refs."
    lines: list[str] = []
    for item in summary.recent_javascript[:3]:
        ref_type = _safe_short(item.get("reference_type")) or "ref"
        source = _safe_short(item.get("source_url_excerpt"), limit=80) or "unknown-source"
        target = _safe_short(item.get("referenced_url_excerpt"), limit=120) or "unknown-target"
        lines.append(f"{ref_type}: {source} -> {target}")
    return "Последние JS refs: " + "; ".join(lines) + "."


def _surface_next_step(summary: ContextRefSummary) -> str:
    endpoints = summary.surface_counts.get("endpoints", 0)
    js = summary.surface_counts.get("javascript_references", 0)
    if summary.recent_http:
        return "Следующий шаг: сгруппировать последние HTTP observations по веткам и выделить новые/изменившиеся пути для решения человека."
    if endpoints or js:
        return "Следующий шаг: запросить свежий surface delta или samples, чтобы отличить реальный прирост от старого охвата."
    return "Следующий шаг: сначала собрать surface summary; без него агент поверхности должен остановиться."


def _artifact_next_step(summary: ContextRefSummary) -> str:
    if summary.recent_javascript:
        return "Следующий шаг: выделить из JS refs новые пути и параметры, затем создать bounded proposal на passive review этих refs."
    if summary.surface_counts.get("http_observations", 0):
        return "Следующий шаг: сравнить HTTP observations с уже известными endpoints и найти parser gaps или новые параметры."
    return "Следующий шаг: запросить artifact/fact refs; без них агент артефактов должен остановиться."


def _critic_risk_brief(summary: ContextRefSummary) -> str:
    risks: list[str] = []
    low_gain = [item for item in summary.recent_outcomes if float(item.get("information_gain_score") or 0.0) < 0.15]
    stopped = [item for item in summary.recent_outcomes if _human_feedback_flag(item, "manual_stop")]
    high_stop_proposals = [
        item
        for item in summary.pending_proposals
        if float(item.get("human_stop_rate") or 0.0) >= 0.3
    ]
    if low_gain:
        risks.append(f"низкий information gain у {len(low_gain)} recent outcomes")
    if stopped:
        risks.append(f"manual stop у {len(stopped)} outcomes")
    if high_stop_proposals:
        risks.append(f"высокий human_stop_rate у {len(high_stop_proposals)} pending proposals")
    if not risks:
        return "Явных stop-сигналов в compact context не вижу. Всё равно нужен bounded запуск через ActionService, если появится proposal."
    return "Риски/шум: " + "; ".join(risks) + "."


def _critic_next_step(summary: ContextRefSummary) -> str:
    if _has_stop_signal(summary):
        return "Следующий шаг: сузить ветку или запросить объяснение, почему новый сигнал сильнее прошлых stop/noise отметок."
    if summary.pending_proposal_count:
        return "Следующий шаг: проверить лучший pending proposal на повторяемость, scope и ожидаемый gain перед accept."
    return "Следующий шаг: попросить агента приложить refs/outcomes; без них критик не должен утверждать, что направление полезно."


def _report_readiness_brief(summary: ContextRefSummary) -> str:
    evidence_refs = summary.refs_by_kind.get("evidence", ())
    action_refs = summary.refs_by_kind.get("action", ()) or summary.refs_by_kind.get("action-request", ())
    if evidence_refs and action_refs:
        return f"Есть evidence refs: {len(evidence_refs)} и action refs: {len(action_refs)}. Можно готовить структуру отчёта, но без raw bodies."
    if evidence_refs:
        return f"Есть evidence refs: {len(evidence_refs)}. Не хватает связанного action/outcome context для воспроизводимости."
    return "Evidence refs не приложены. Отчёт пока рано собирать; сначала нужна доказательная цепочка."


def _coordinator_next_step(summary: ContextRefSummary) -> str:
    if summary.pending_proposal_count:
        return "Следующий безопасный шаг: разобрать pending proposal из опыта и решить: принять, сузить или подавить как шум."
    if summary.recent_javascript:
        return "Следующий безопасный шаг: отдать JS refs агенту артефактов и подготовить passive proposal по новым путям."
    if summary.recent_http or summary.surface_counts.get("endpoints", 0):
        return "Следующий безопасный шаг: отдать свежую поверхность surface-агенту, чтобы выделить ветки с реальным приростом."
    if summary.recent_outcome_count:
        return "Следующий безопасный шаг: посмотреть последние outcomes и выбрать действие с максимальным gain/cost, без автозапуска."
    return "Следующий безопасный шаг: запросить compact context по кампании. Сейчас можно только уточнить задачу текстом."


def _coordinator_proposal_title(summary: ContextRefSummary) -> str:
    if summary.pending_proposal_count:
        return "Разобрать pending proposal из опыта"
    if summary.recent_javascript:
        return "Разобрать JS refs как следующую ветку"
    if summary.recent_http:
        return "Разобрать свежие HTTP observations"
    return "Разложить задачу на безопасные следующие шаги"


def _surface_proposal_title(summary: ContextRefSummary) -> str:
    if summary.recent_http:
        return "Сгруппировать свежие HTTP observations по веткам"
    return "Разобрать изменения поверхности"


def _artifact_proposal_title(summary: ContextRefSummary) -> str:
    if summary.recent_javascript:
        return "Извлечь новые пути из JS refs"
    return "Разобрать новые артефакты и JS-пути"


def _critic_proposal_title(summary: ContextRefSummary) -> str:
    if _has_stop_signal(summary):
        return "Проверить stop/noise сигналы перед продолжением"
    return "Проверить ветку на шум и повторы"


def _coordinator_priority(summary: ContextRefSummary) -> str:
    if summary.pending_proposal_count or summary.recent_javascript:
        return "high"
    if summary.recent_outcome_count or _has_surface_signal(summary):
        return "medium"
    return "low"


def _coordinator_expected_gain(summary: ContextRefSummary) -> str:
    if summary.pending_proposal_count:
        return "Использовать прошлый опыт и human feedback для выбора следующего bounded шага."
    if summary.recent_javascript:
        return "Найти новые пути/параметры из JS refs без чтения raw output."
    if _has_surface_signal(summary):
        return "Сузить исследование до изменившихся веток поверхности."
    return "Уточнить задачу и получить compact context перед запуском чего-либо."


def _has_surface_signal(summary: ContextRefSummary) -> bool:
    return bool(summary.recent_http or summary.recent_javascript or any(summary.surface_counts.values()))


def _has_stop_signal(summary: ContextRefSummary) -> bool:
    if any(_human_feedback_flag(item, "manual_stop") for item in summary.recent_outcomes):
        return True
    if any(float(item.get("information_gain_score") or 0.0) < 0.05 for item in summary.recent_outcomes):
        return True
    return any(float(item.get("human_stop_rate") or 0.0) >= 0.3 for item in summary.pending_proposals)


def _human_feedback_flag(item: dict[str, Any], key: str) -> bool:
    feedback = item.get("human_feedback") if isinstance(item.get("human_feedback"), dict) else {}
    return bool(feedback.get(key))


def _nonzero_count_line(counts: dict[str, Any], *, keys: tuple[str, ...]) -> str:
    parts: list[str] = []
    for key in keys:
        value = counts.get(key)
        if isinstance(value, (int, float)) and value:
            parts.append(f"{key} {int(value)}")
    return ", ".join(parts)

def _join_sections(*sections: str) -> str:
    return "\n\n".join(section.strip() for section in sections if section and section.strip())
