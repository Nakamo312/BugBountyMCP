from __future__ import annotations


def _surface_node_projection_query(snapshot_parameter: str) -> str:
    return (
        "'MATCH (n:SurfaceNode {program_id: $program_id, "
        f"snapshot_id: ${snapshot_parameter}}}) RETURN id(n) AS id'"
    )


def _surface_edge_projection_query(snapshot_parameter: str) -> str:
    return (
        "'MATCH (a:SurfaceNode {program_id: $program_id, "
        f"snapshot_id: ${snapshot_parameter}}})-[r:SURFACE_EDGE]-(b:SurfaceNode {{program_id: $program_id, "
        f"snapshot_id: ${snapshot_parameter}}}) RETURN id(a) AS source, id(b) AS target, "
        "coalesce(r.weight, 1.0) AS weight'"
    )


def _surface_snapshot_projection_call(
    graph_parameter: str,
    snapshot_parameter: str,
    yielded_graph_name: str = "graphName",
) -> str:
    return "\n".join(
        (
            "CALL gds.graph.project.cypher(",
            f"  ${graph_parameter},",
            f"  {_surface_node_projection_query(snapshot_parameter)},",
            f"  {_surface_edge_projection_query(snapshot_parameter)},",
            "  {parameters: {"
            f"program_id: $program_id, {snapshot_parameter}: ${snapshot_parameter}"
            "}, relationshipProperties: 'weight'}",
            ")",
            f"YIELD {yielded_graph_name}",
        )
    )


SURFACE_WCC_CYPHER = """
MATCH (snapshot:SurfaceSnapshot {program_id: $program_id, snapshot_id: $snapshot_id})
WITH snapshot
__SURFACE_SNAPSHOT_PROJECTION__
CALL gds.wcc.stream(graphName)
YIELD nodeId, componentId
WITH graphName, gds.util.asNode(nodeId) AS node, componentId
OPTIONAL MATCH (:SurfaceSnapshot {program_id: $program_id, snapshot_id: $snapshot_id})-[:HAS_SURFACE_DELTA]->(delta:SurfaceDelta {program_id: $program_id, snapshot_id: $snapshot_id})
WHERE delta.subject_fingerprint = node.node_fingerprint
WITH graphName,
     componentId,
     count(DISTINCT node) AS node_count,
     avg(toFloat(coalesce(delta.novelty_score, 0))) AS avg_novelty_score,
     max(toInteger(coalesce(delta.novelty_score, 0))) AS max_novelty_score
CALL gds.graph.drop(graphName, false) YIELD graphName AS droppedGraphName
RETURN componentId AS component_id,
       node_count,
       coalesce(avg_novelty_score, 0.0) AS avg_novelty_score,
       coalesce(max_novelty_score, 0) AS max_novelty_score
ORDER BY max_novelty_score DESC, node_count DESC
LIMIT $limit
"""
SURFACE_WCC_CYPHER = SURFACE_WCC_CYPHER.replace("__SURFACE_SNAPSHOT_PROJECTION__", _surface_snapshot_projection_call('graph_name', 'snapshot_id'))
SURFACE_WCC_CYPHER = SURFACE_WCC_CYPHER.strip()


SURFACE_COMPONENT_PROFILE_CYPHER = """
MATCH (snapshot:SurfaceSnapshot {program_id: $program_id, snapshot_id: $snapshot_id})
WITH snapshot
__SURFACE_SNAPSHOT_PROJECTION__
CALL gds.wcc.stream(graphName)
YIELD nodeId, componentId
WITH graphName, collect({nodeId: nodeId, componentId: componentId}) AS memberships
CALL gds.degree.stream(graphName)
YIELD nodeId, score
WITH graphName,
     memberships,
     collect({nodeId: nodeId, degree_score: toFloat(score)}) AS degree_rows
UNWIND memberships AS membership
WITH graphName,
     membership.componentId AS componentId,
     gds.util.asNode(membership.nodeId) AS node,
     coalesce(head([row IN degree_rows WHERE row.nodeId = membership.nodeId | row.degree_score]), 0.0) AS degree_score
OPTIONAL MATCH (:SurfaceSnapshot {program_id: $program_id, snapshot_id: $snapshot_id})-[:HAS_SURFACE_DELTA]->(delta:SurfaceDelta {program_id: $program_id, snapshot_id: $snapshot_id})
WHERE delta.subject_fingerprint = node.node_fingerprint
WITH graphName,
     componentId,
     node,
     degree_score,
     max(toFloat(coalesce(delta.novelty_score, 0))) AS node_novelty_score
WITH graphName,
     componentId,
     count(DISTINCT node) AS node_count,
     count(DISTINCT CASE WHEN node_novelty_score > 0 THEN node END) AS changed_node_count,
     avg(node_novelty_score) AS avg_novelty_score,
     max(toInteger(node_novelty_score)) AS max_novelty_score,
     avg(degree_score) AS avg_degree,
     max(degree_score) AS max_degree
CALL gds.graph.drop(graphName, false) YIELD graphName AS droppedGraphName
RETURN componentId AS component_id,
       node_count,
       changed_node_count,
       coalesce(avg_novelty_score, 0.0) AS avg_novelty_score,
       coalesce(max_novelty_score, 0) AS max_novelty_score,
       coalesce(avg_degree, 0.0) AS avg_degree,
       coalesce(max_degree, 0.0) AS max_degree
"""
SURFACE_COMPONENT_PROFILE_CYPHER = SURFACE_COMPONENT_PROFILE_CYPHER.replace("__SURFACE_SNAPSHOT_PROJECTION__", _surface_snapshot_projection_call('graph_name', 'snapshot_id'))
SURFACE_COMPONENT_PROFILE_CYPHER = SURFACE_COMPONENT_PROFILE_CYPHER.strip()


SURFACE_COMPONENT_BRIDGE_CYPHER = """
MATCH (snapshot:SurfaceSnapshot {program_id: $program_id, snapshot_id: $snapshot_id})
WITH snapshot
__SURFACE_SNAPSHOT_PROJECTION__
CALL gds.wcc.stream(graphName)
YIELD nodeId, componentId
WITH graphName, collect({nodeId: nodeId, componentId: componentId}) AS memberships
CALL gds.degree.stream(graphName)
YIELD nodeId, score
WITH graphName,
     memberships,
     collect({nodeId: nodeId, degree_score: toFloat(score)}) AS degree_rows
CALL gds.betweenness.stream(graphName)
YIELD nodeId, score
WITH graphName,
     memberships,
     degree_rows,
     collect({nodeId: nodeId, betweenness_score: toFloat(score)}) AS betweenness_rows
UNWIND memberships AS membership
WITH graphName,
     membership.componentId AS componentId,
     gds.util.asNode(membership.nodeId) AS node,
     coalesce(head([row IN degree_rows WHERE row.nodeId = membership.nodeId | row.degree_score]), 0.0) AS degree_score,
     coalesce(head([row IN betweenness_rows WHERE row.nodeId = membership.nodeId | row.betweenness_score]), 0.0) AS betweenness_score
OPTIONAL MATCH (:SurfaceSnapshot {program_id: $program_id, snapshot_id: $snapshot_id})-[:HAS_SURFACE_DELTA]->(delta:SurfaceDelta {program_id: $program_id, snapshot_id: $snapshot_id})
WHERE delta.subject_fingerprint = node.node_fingerprint
WITH graphName,
     componentId,
     node,
     degree_score,
     betweenness_score,
     max(toFloat(coalesce(delta.novelty_score, 0))) AS node_novelty_score
WITH graphName,
     componentId,
     count(DISTINCT node) AS node_count,
     count(DISTINCT CASE WHEN node_novelty_score > 0 THEN node END) AS changed_node_count,
     avg(betweenness_score) AS avg_betweenness,
     max(betweenness_score) AS max_betweenness,
     avg(degree_score) AS avg_degree,
     max(degree_score) AS max_degree,
     max(toInteger(node_novelty_score)) AS max_novelty_score
CALL gds.graph.drop(graphName, false) YIELD graphName AS droppedGraphName
RETURN componentId AS component_id,
       node_count,
       changed_node_count,
       coalesce(avg_betweenness, 0.0) AS avg_betweenness,
       coalesce(max_betweenness, 0.0) AS max_betweenness,
       coalesce(avg_degree, 0.0) AS avg_degree,
       coalesce(max_degree, 0.0) AS max_degree,
       coalesce(max_novelty_score, 0) AS max_novelty_score
"""
SURFACE_COMPONENT_BRIDGE_CYPHER = SURFACE_COMPONENT_BRIDGE_CYPHER.replace("__SURFACE_SNAPSHOT_PROJECTION__", _surface_snapshot_projection_call('graph_name', 'snapshot_id'))
SURFACE_COMPONENT_BRIDGE_CYPHER = SURFACE_COMPONENT_BRIDGE_CYPHER.strip()


SURFACE_COMPONENT_OUTLIER_CYPHER = """
MATCH (snapshot:SurfaceSnapshot {program_id: $program_id, snapshot_id: $snapshot_id})
WITH snapshot
__SURFACE_SNAPSHOT_PROJECTION__
CALL gds.wcc.stream(graphName)
YIELD nodeId, componentId
WITH graphName, collect({nodeId: nodeId, componentId: componentId}) AS memberships
CALL gds.nodeSimilarity.stream(graphName, {similarityCutoff: $similarity_cutoff, topK: $top_k})
YIELD node1, node2, similarity
WITH graphName,
     memberships,
     collect({node1: node1, node2: node2, similarity_score: toFloat(similarity)}) AS similarity_rows
UNWIND memberships AS membership
WITH graphName,
     membership.componentId AS componentId,
     gds.util.asNode(membership.nodeId) AS node,
     coalesce(
       reduce(best = 0.0, row IN similarity_rows |
         CASE
           WHEN row.node1 = membership.nodeId OR row.node2 = membership.nodeId
           THEN CASE WHEN row.similarity_score > best THEN row.similarity_score ELSE best END
           ELSE best
         END
       ),
       0.0
     ) AS node_similarity
OPTIONAL MATCH (:SurfaceSnapshot {program_id: $program_id, snapshot_id: $snapshot_id})-[:HAS_SURFACE_DELTA]->(delta:SurfaceDelta {program_id: $program_id, snapshot_id: $snapshot_id})
WHERE delta.subject_fingerprint = node.node_fingerprint
WITH graphName,
     componentId,
     node,
     node_similarity,
     max(toFloat(coalesce(delta.novelty_score, 0))) AS node_novelty_score
WITH graphName,
     componentId,
     count(DISTINCT node) AS node_count,
     count(DISTINCT CASE WHEN node_novelty_score > 0 THEN node END) AS changed_node_count,
     count(DISTINCT CASE WHEN node_similarity < 0.15 THEN node END) AS low_similarity_node_count,
     avg(node_similarity) AS avg_similarity,
     max(node_similarity) AS max_similarity,
     max(toInteger(node_novelty_score)) AS max_novelty_score
CALL gds.graph.drop(graphName, false) YIELD graphName AS droppedGraphName
RETURN componentId AS component_id,
       node_count,
       changed_node_count,
       coalesce(avg_similarity, 0.0) AS avg_similarity,
       coalesce(max_similarity, 0.0) AS max_similarity,
       low_similarity_node_count,
       coalesce(max_novelty_score, 0) AS max_novelty_score
"""
SURFACE_COMPONENT_OUTLIER_CYPHER = SURFACE_COMPONENT_OUTLIER_CYPHER.replace("__SURFACE_SNAPSHOT_PROJECTION__", _surface_snapshot_projection_call('graph_name', 'snapshot_id'))
SURFACE_COMPONENT_OUTLIER_CYPHER = SURFACE_COMPONENT_OUTLIER_CYPHER.strip()


SURFACE_COMPONENT_COVERAGE_CYPHER = """
MATCH (snapshot:SurfaceSnapshot {program_id: $program_id, snapshot_id: $snapshot_id})
WITH snapshot
__SURFACE_SNAPSHOT_PROJECTION__
CALL gds.wcc.stream(graphName)
YIELD nodeId, componentId
WITH graphName,
     componentId,
     collect(DISTINCT gds.util.asNode(nodeId).node_fingerprint) AS node_fingerprints
OPTIONAL MATCH (snapshot:SurfaceSnapshot {program_id: $program_id, snapshot_id: $snapshot_id})-[:HAS_SURFACE_DELTA]->(delta:SurfaceDelta {program_id: $program_id, snapshot_id: $snapshot_id})
WHERE delta.subject_fingerprint IN node_fingerprints
WITH graphName,
     componentId,
     node_fingerprints,
     collect(DISTINCT delta.subject_fingerprint) AS changed_fingerprints,
     max(toInteger(coalesce(delta.novelty_score, 0))) AS max_novelty_score
OPTIONAL MATCH (outcome:ActionOutcome {program_id: $program_id})-[:AFTER_SURFACE_SNAPSHOT]->(:SurfaceSnapshot {program_id: $program_id, snapshot_id: $snapshot_id})-[:HAS_SURFACE_DELTA]->(covered_delta:SurfaceDelta {program_id: $program_id, snapshot_id: $snapshot_id})
WHERE covered_delta.subject_fingerprint IN node_fingerprints
WITH graphName,
     componentId,
     node_fingerprints,
     changed_fingerprints,
     max_novelty_score,
     collect(DISTINCT outcome) AS outcomes
CALL gds.graph.drop(graphName, false) YIELD graphName AS droppedGraphName
RETURN componentId AS component_id,
       size(node_fingerprints) AS node_count,
       size([fingerprint IN changed_fingerprints WHERE fingerprint IS NOT NULL]) AS changed_node_count,
       size([outcome IN outcomes WHERE outcome IS NOT NULL]) AS action_outcome_count,
       size([outcome IN outcomes WHERE coalesce(outcome.manual_interest, false) OR coalesce(outcome.continued_by_followup, false) OR coalesce(outcome.report_created, false)]) AS positive_outcome_count,
       size([outcome IN outcomes WHERE coalesce(outcome.manual_stop, false)]) AS stop_outcome_count,
       CASE WHEN size([outcome IN outcomes WHERE outcome IS NOT NULL]) = 0
            THEN 0.0
            ELSE reduce(total = 0.0, outcome IN [item IN outcomes WHERE item IS NOT NULL] | total + toFloat(coalesce(outcome.information_gain_score, 0.0)))
                 / toFloat(size([outcome IN outcomes WHERE outcome IS NOT NULL]))
       END AS avg_outcome_utility,
       coalesce(max_novelty_score, 0) AS max_novelty_score
"""
SURFACE_COMPONENT_COVERAGE_CYPHER = SURFACE_COMPONENT_COVERAGE_CYPHER.replace("__SURFACE_SNAPSHOT_PROJECTION__", _surface_snapshot_projection_call('graph_name', 'snapshot_id'))
SURFACE_COMPONENT_COVERAGE_CYPHER = SURFACE_COMPONENT_COVERAGE_CYPHER.strip()


SURFACE_COMPONENT_ACTION_CANDIDATE_CYPHER = """
__SURFACE_WCC_CANDIDATE_PROJECTION__
CALL gds.wcc.stream(wccGraphName)
YIELD nodeId, componentId
WITH wccGraphName,
     componentId,
     collect(DISTINCT gds.util.asNode(nodeId).node_fingerprint) AS node_fingerprints
OPTIONAL MATCH (:SurfaceSnapshot {program_id: $program_id, snapshot_id: $snapshot_id})-[:HAS_SURFACE_DELTA]->(delta:SurfaceDelta {program_id: $program_id, snapshot_id: $snapshot_id})
WHERE delta.subject_fingerprint IN node_fingerprints
WITH wccGraphName,
     componentId,
     node_fingerprints,
     collect(DISTINCT delta.subject_fingerprint) AS changed_fingerprints,
     max(toInteger(coalesce(delta.novelty_score, 0))) AS max_novelty_score
WITH wccGraphName,
     collect({
       component_id: componentId,
       node_fingerprints: node_fingerprints,
       changed_node_count: size([fingerprint IN changed_fingerprints WHERE fingerprint IS NOT NULL]),
       max_novelty_score: coalesce(max_novelty_score, 0)
     }) AS components
CALL gds.graph.drop(wccGraphName, false) YIELD graphName AS droppedWccGraphName
WITH components
UNWIND components AS component
WITH component
ORDER BY component.max_novelty_score DESC, component.changed_node_count DESC, size(component.node_fingerprints) DESC
LIMIT $component_limit
OPTIONAL MATCH (component_fingerprint:SurfaceFingerprint {program_id: $program_id})
WHERE component_fingerprint.fingerprint IN component.node_fingerprints
WITH component,
     collect(DISTINCT component_fingerprint.fingerprint) AS component_fingerprints
MATCH (outcome:ActionOutcome {program_id: $program_id})
WHERE outcome.capability_id IS NOT NULL
  AND outcome.profile_id IS NOT NULL
MATCH (outcome)-[:AFTER_SURFACE_SNAPSHOT]->(:SurfaceSnapshot {program_id: $program_id})-[:HAS_SURFACE_DELTA]->(outcome_delta:SurfaceDelta {program_id: $program_id})
MATCH (outcome_fingerprint:SurfaceFingerprint {program_id: $program_id, fingerprint: outcome_delta.subject_fingerprint})
WITH component,
     component_fingerprints,
     outcome,
     collect(DISTINCT outcome_fingerprint.fingerprint) AS outcome_fingerprints
WITH component,
     outcome,
     size([fingerprint IN component_fingerprints WHERE fingerprint IN outcome_fingerprints]) AS intersection_size,
     size(component_fingerprints + [fingerprint IN outcome_fingerprints WHERE NOT (fingerprint IN component_fingerprints)]) AS union_size
WITH component,
     outcome,
     CASE WHEN union_size = 0 THEN 0.0 ELSE toFloat(intersection_size) / toFloat(union_size) END AS similarity
WHERE similarity >= $similarity_cutoff
WITH component.component_id AS component_id,
     size(component.node_fingerprints) AS node_count,
     component.changed_node_count AS changed_node_count,
     component.max_novelty_score AS max_novelty_score,
     outcome.capability_id AS capability_id,
     outcome.profile_id AS profile_id,
     count(outcome) AS sample_count,
     avg(similarity) AS avg_similarity,
     avg(coalesce(outcome.information_gain_score, 0.0)) AS avg_information_gain_score,
     avg(CASE WHEN coalesce(outcome.manual_interest, false) OR coalesce(outcome.continued_by_followup, false) OR coalesce(outcome.report_created, false) THEN 1.0 ELSE 0.0 END) AS human_positive_rate,
     avg(CASE WHEN coalesce(outcome.manual_stop, false) THEN 1.0 ELSE 0.0 END) AS human_stop_rate
WITH component_id,
     node_count,
     changed_node_count,
     max_novelty_score,
     capability_id,
     profile_id,
     sample_count,
     avg_similarity,
     avg_information_gain_score,
     human_positive_rate,
     human_stop_rate,
     (toFloat(sample_count) / (toFloat(sample_count) + 5.0)) AS confidence_score
WITH component_id,
     node_count,
     changed_node_count,
     max_novelty_score,
     capability_id,
     profile_id,
     sample_count,
     avg_similarity,
     avg_information_gain_score,
     human_positive_rate,
     human_stop_rate,
     (avg_information_gain_score * avg_similarity * confidence_score * (1.0 + human_positive_rate)) / (1.0 + human_stop_rate) AS utility_score
RETURN component_id,
       node_count,
       changed_node_count,
       max_novelty_score,
       capability_id,
       profile_id,
       sample_count,
       avg_similarity,
       avg_information_gain_score,
       human_positive_rate,
       human_stop_rate,
       utility_score
ORDER BY utility_score DESC, sample_count DESC
LIMIT $limit
"""
SURFACE_COMPONENT_ACTION_CANDIDATE_CYPHER = SURFACE_COMPONENT_ACTION_CANDIDATE_CYPHER.replace("__SURFACE_WCC_CANDIDATE_PROJECTION__", _surface_snapshot_projection_call('wcc_graph_name', 'snapshot_id', 'graphName AS wccGraphName'))
SURFACE_COMPONENT_ACTION_CANDIDATE_CYPHER = SURFACE_COMPONENT_ACTION_CANDIDATE_CYPHER.strip()


SURFACE_COMPONENT_DRIFT_CYPHER = """
__CURRENT_SURFACE_SNAPSHOT_PROJECTION__
CALL gds.wcc.stream(currentGraphName)
YIELD nodeId, componentId
WITH currentGraphName,
     collect({
       node_fingerprint: gds.util.asNode(nodeId).node_fingerprint,
       component_id: componentId
     }) AS current_memberships
CALL gds.graph.drop(currentGraphName, false) YIELD graphName AS droppedCurrentGraphName
WITH current_memberships
__PREVIOUS_SURFACE_SNAPSHOT_PROJECTION__
CALL gds.wcc.stream(previousGraphName)
YIELD nodeId, componentId
WITH current_memberships,
     previousGraphName,
     collect({
       node_fingerprint: gds.util.asNode(nodeId).node_fingerprint,
       component_id: componentId
     }) AS previous_memberships
CALL gds.graph.drop(previousGraphName, false) YIELD graphName AS droppedPreviousGraphName
WITH current_memberships, previous_memberships
UNWIND current_memberships AS current_member
WITH previous_memberships,
     current_member.component_id AS current_component_id,
     collect(DISTINCT current_member.node_fingerprint) AS current_nodes
WITH previous_memberships,
     collect({component_id: current_component_id, nodes: current_nodes}) AS current_components
UNWIND previous_memberships AS previous_member
WITH current_components,
     previous_member.component_id AS previous_component_id,
     collect(DISTINCT previous_member.node_fingerprint) AS previous_nodes
WITH current_components,
     collect({component_id: previous_component_id, nodes: previous_nodes}) AS previous_components
UNWIND current_components AS current_component
UNWIND previous_components AS previous_component
WITH current_component,
     previous_component,
     [node_fingerprint IN current_component.nodes WHERE node_fingerprint IN previous_component.nodes] AS shared_nodes
WITH current_component,
     previous_component,
     shared_nodes,
     size(current_component.nodes) AS current_node_count,
     size(previous_component.nodes) AS previous_node_count,
     size(shared_nodes) AS shared_node_count,
     size(current_component.nodes) + size(previous_component.nodes) - size(shared_nodes) AS union_node_count
WITH current_component,
     previous_component,
     current_node_count,
     previous_node_count,
     shared_node_count,
     CASE WHEN union_node_count = 0 THEN 0.0 ELSE toFloat(shared_node_count) / toFloat(union_node_count) END AS jaccard_similarity
ORDER BY current_component.component_id ASC, jaccard_similarity DESC, shared_node_count DESC, previous_node_count DESC
WITH current_component,
     collect({
       previous_component_id: previous_component.component_id,
       previous_node_count: previous_node_count,
       shared_node_count: shared_node_count,
       jaccard_similarity: jaccard_similarity
     })[0] AS best_previous
OPTIONAL MATCH (:SurfaceSnapshot {program_id: $program_id, snapshot_id: $current_snapshot_id})-[:HAS_SURFACE_DELTA]->(delta:SurfaceDelta {program_id: $program_id, snapshot_id: $current_snapshot_id})
WHERE delta.subject_fingerprint IN current_component.nodes
WITH current_component,
     best_previous,
     count(DISTINCT delta.subject_fingerprint) AS changed_node_count,
     avg(toFloat(coalesce(delta.novelty_score, 0))) AS avg_novelty_score,
     max(toInteger(coalesce(delta.novelty_score, 0))) AS max_novelty_score
RETURN current_component.component_id AS current_component_id,
       best_previous.previous_component_id AS previous_component_id,
       size(current_component.nodes) AS current_node_count,
       best_previous.previous_node_count AS previous_node_count,
       best_previous.shared_node_count AS shared_node_count,
       size(current_component.nodes) - best_previous.shared_node_count AS introduced_node_count,
       best_previous.previous_node_count - best_previous.shared_node_count AS removed_node_count,
       best_previous.jaccard_similarity AS jaccard_similarity,
       coalesce(avg_novelty_score, 0.0) AS avg_novelty_score,
       coalesce(max_novelty_score, 0) AS max_novelty_score
"""
SURFACE_COMPONENT_DRIFT_CYPHER = SURFACE_COMPONENT_DRIFT_CYPHER.replace("__CURRENT_SURFACE_SNAPSHOT_PROJECTION__", _surface_snapshot_projection_call('current_graph_name', 'current_snapshot_id', 'graphName AS currentGraphName'))
SURFACE_COMPONENT_DRIFT_CYPHER = SURFACE_COMPONENT_DRIFT_CYPHER.replace("__PREVIOUS_SURFACE_SNAPSHOT_PROJECTION__", _surface_snapshot_projection_call('previous_graph_name', 'previous_snapshot_id', 'graphName AS previousGraphName'))
SURFACE_COMPONENT_DRIFT_CYPHER = SURFACE_COMPONENT_DRIFT_CYPHER.strip()
