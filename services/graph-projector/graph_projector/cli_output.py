from __future__ import annotations


def _print_surface_component_report(report) -> None:
    print(
        "graph-projector surface-components: "
        f"program_id={report.program_id} snapshot_id={report.snapshot_id} "
        f"previous_snapshot_id={report.previous_snapshot_id or '-'} "
        f"profiles={len(report.profiles)} drift={len(report.drift)} "
        f"bridges={len(report.bridges)} outliers={len(report.outliers)} "
        f"coverage={len(report.coverage)} action_candidates={len(report.action_candidates)}"
    )
    for item in report.profiles:
        print(
            "surface_component_profile "
            f"component_id={item.component_id} node_count={item.node_count} "
            f"changed_node_count={item.changed_node_count} "
            f"structural_pressure_score={item.structural_pressure_score} "
            f"max_novelty_score={item.max_novelty_score}"
        )
    for item in report.drift:
        print(
            "surface_component_drift "
            f"component_id={item.current_component_id} "
            f"previous_component_id={item.previous_component_id} "
            f"drift_score={item.drift_score} jaccard_similarity={item.jaccard_similarity:.4f} "
            f"introduced_node_count={item.introduced_node_count} removed_node_count={item.removed_node_count}"
        )
    for item in report.bridges:
        print(
            "surface_component_bridge "
            f"component_id={item.component_id} bridge_pressure_score={item.bridge_pressure_score} "
            f"max_betweenness={item.max_betweenness:.4f} max_degree={item.max_degree:.4f}"
        )
    for item in report.outliers:
        print(
            "surface_component_outlier "
            f"component_id={item.component_id} outlier_score={item.outlier_score} "
            f"avg_similarity={item.avg_similarity:.4f} low_similarity_node_count={item.low_similarity_node_count}"
        )
    for item in report.coverage:
        print(
            "surface_component_coverage "
            f"component_id={item.component_id} coverage_score={item.coverage_score} "
            f"exploration_priority_score={item.exploration_priority_score} "
            f"action_outcome_count={item.action_outcome_count}"
        )
    for item in report.action_candidates:
        print(
            "surface_component_action_candidate "
            f"component_id={item.component_id} capability_id={item.capability_id} profile_id={item.profile_id} "
            f"candidate_score={item.candidate_score} sample_count={item.sample_count} "
            f"avg_similarity={item.avg_similarity:.4f}"
        )
