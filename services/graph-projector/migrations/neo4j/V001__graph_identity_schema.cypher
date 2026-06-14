CREATE CONSTRAINT graph_node_program_identity IF NOT EXISTS
FOR (node:Program)
REQUIRE (node.program_id, node.key) IS UNIQUE;

CREATE CONSTRAINT graph_node_scope_identity IF NOT EXISTS
FOR (node:Scope)
REQUIRE (node.program_id, node.key) IS UNIQUE;

CREATE CONSTRAINT graph_node_host_identity IF NOT EXISTS
FOR (node:Host)
REQUIRE (node.program_id, node.key) IS UNIQUE;

CREATE CONSTRAINT graph_node_ip_identity IF NOT EXISTS
FOR (node:IP)
REQUIRE (node.program_id, node.key) IS UNIQUE;

CREATE CONSTRAINT graph_node_asn_identity IF NOT EXISTS
FOR (node:ASN)
REQUIRE (node.program_id, node.key) IS UNIQUE;

CREATE CONSTRAINT graph_node_cidr_identity IF NOT EXISTS
FOR (node:CIDR)
REQUIRE (node.program_id, node.key) IS UNIQUE;

CREATE CONSTRAINT graph_node_service_identity IF NOT EXISTS
FOR (node:Service)
REQUIRE (node.program_id, node.key) IS UNIQUE;

CREATE CONSTRAINT graph_node_endpoint_identity IF NOT EXISTS
FOR (node:Endpoint)
REQUIRE (node.program_id, node.key) IS UNIQUE;

CREATE CONSTRAINT graph_node_tool_identity IF NOT EXISTS
FOR (node:Tool)
REQUIRE (node.program_id, node.key) IS UNIQUE;

CREATE CONSTRAINT graph_node_toolrun_identity IF NOT EXISTS
FOR (node:ToolRun)
REQUIRE (node.program_id, node.key) IS UNIQUE;

CREATE CONSTRAINT graph_node_artifact_identity IF NOT EXISTS
FOR (node:Artifact)
REQUIRE (node.program_id, node.key) IS UNIQUE;

CREATE CONSTRAINT graph_node_observation_identity IF NOT EXISTS
FOR (node:Observation)
REQUIRE (node.program_id, node.key) IS UNIQUE;

CREATE CONSTRAINT graph_node_evidence_identity IF NOT EXISTS
FOR (node:Evidence)
REQUIRE (node.program_id, node.key) IS UNIQUE;

CREATE INDEX graph_rel_has_scope_identity IF NOT EXISTS
FOR ()-[rel:HAS_SCOPE]-()
ON (rel.identity_key);

CREATE INDEX graph_rel_matches_scope_identity IF NOT EXISTS
FOR ()-[rel:MATCHES_SCOPE]-()
ON (rel.identity_key);

CREATE INDEX graph_rel_resolves_to_identity IF NOT EXISTS
FOR ()-[rel:RESOLVES_TO]-()
ON (rel.identity_key);

CREATE INDEX graph_rel_in_cidr_identity IF NOT EXISTS
FOR ()-[rel:IN_CIDR]-()
ON (rel.identity_key);

CREATE INDEX graph_rel_announced_by_identity IF NOT EXISTS
FOR ()-[rel:ANNOUNCED_BY]-()
ON (rel.identity_key);

CREATE INDEX graph_rel_exposes_service_identity IF NOT EXISTS
FOR ()-[rel:EXPOSES_SERVICE]-()
ON (rel.identity_key);

CREATE INDEX graph_rel_has_endpoint_identity IF NOT EXISTS
FOR ()-[rel:HAS_ENDPOINT]-()
ON (rel.identity_key);

CREATE INDEX graph_rel_has_tool_run_identity IF NOT EXISTS
FOR ()-[rel:HAS_TOOL_RUN]-()
ON (rel.identity_key);

CREATE INDEX graph_rel_used_tool_identity IF NOT EXISTS
FOR ()-[rel:USED_TOOL]-()
ON (rel.identity_key);

CREATE INDEX graph_rel_produced_artifact_identity IF NOT EXISTS
FOR ()-[rel:PRODUCED_ARTIFACT]-()
ON (rel.identity_key);

CREATE INDEX graph_rel_produced_observation_identity IF NOT EXISTS
FOR ()-[rel:PRODUCED_OBSERVATION]-()
ON (rel.identity_key);

CREATE INDEX graph_rel_describes_identity IF NOT EXISTS
FOR ()-[rel:DESCRIBES]-()
ON (rel.identity_key);

CREATE INDEX graph_rel_supports_evidence_identity IF NOT EXISTS
FOR ()-[rel:SUPPORTS_EVIDENCE]-()
ON (rel.identity_key);

CREATE INDEX graph_rel_derived_from_identity IF NOT EXISTS
FOR ()-[rel:DERIVED_FROM]-()
ON (rel.identity_key);
