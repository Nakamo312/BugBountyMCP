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

CREATE CONSTRAINT graph_node_parameter_identity IF NOT EXISTS
FOR (node:Parameter)
REQUIRE (node.program_id, node.key) IS UNIQUE;

CREATE CONSTRAINT graph_node_requestshape_identity IF NOT EXISTS
FOR (node:RequestShape)
REQUIRE (node.program_id, node.key) IS UNIQUE;

CREATE CONSTRAINT graph_node_jsfile_identity IF NOT EXISTS
FOR (node:JSFile)
REQUIRE (node.program_id, node.key) IS UNIQUE;

CREATE CONSTRAINT graph_node_tool_identity IF NOT EXISTS
FOR (node:Tool)
REQUIRE (node.program_id, node.key) IS UNIQUE;

CREATE CONSTRAINT graph_node_toolrun_identity IF NOT EXISTS
FOR (node:ToolRun)
REQUIRE (node.program_id, node.key) IS UNIQUE;

CREATE CONSTRAINT graph_node_actionoutcome_identity IF NOT EXISTS
FOR (node:ActionOutcome)
REQUIRE (node.program_id, node.key) IS UNIQUE;

CREATE CONSTRAINT graph_node_capabilityprofile_identity IF NOT EXISTS
FOR (node:CapabilityProfile)
REQUIRE (node.program_id, node.key) IS UNIQUE;

CREATE CONSTRAINT graph_node_outcomefeature_identity IF NOT EXISTS
FOR (node:OutcomeFeature)
REQUIRE (node.program_id, node.key) IS UNIQUE;

CREATE CONSTRAINT graph_node_actionexperienceprobe_identity IF NOT EXISTS
FOR (node:ActionExperienceProbe)
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

CREATE CONSTRAINT graph_node_surfacesnapshot_identity IF NOT EXISTS
FOR (node:SurfaceSnapshot)
REQUIRE (node.program_id, node.key) IS UNIQUE;

CREATE CONSTRAINT graph_node_surfacenode_identity IF NOT EXISTS
FOR (node:SurfaceNode)
REQUIRE (node.program_id, node.key) IS UNIQUE;

CREATE CONSTRAINT graph_node_surfacefingerprint_identity IF NOT EXISTS
FOR (node:SurfaceFingerprint)
REQUIRE (node.program_id, node.key) IS UNIQUE;

CREATE CONSTRAINT graph_node_surfacedelta_identity IF NOT EXISTS
FOR (node:SurfaceDelta)
REQUIRE (node.program_id, node.key) IS UNIQUE;

CREATE CONSTRAINT graph_node_surfacecomponentprobe_identity IF NOT EXISTS
FOR (node:SurfaceComponentProbe)
REQUIRE (node.program_id, node.key) IS UNIQUE;

CREATE INDEX graph_rel_has_surface_node_identity IF NOT EXISTS
FOR ()-[rel:HAS_SURFACE_NODE]-()
ON (rel.identity_key);

CREATE INDEX graph_rel_has_surface_fingerprint_identity IF NOT EXISTS
FOR ()-[rel:HAS_SURFACE_FINGERPRINT]-()
ON (rel.identity_key);

CREATE INDEX graph_rel_surface_edge_identity IF NOT EXISTS
FOR ()-[rel:SURFACE_EDGE]-()
ON (rel.identity_key);

CREATE INDEX graph_rel_has_surface_delta_identity IF NOT EXISTS
FOR ()-[rel:HAS_SURFACE_DELTA]-()
ON (rel.identity_key);

CREATE INDEX graph_rel_represents_identity IF NOT EXISTS
FOR ()-[rel:REPRESENTS]-()
ON (rel.identity_key);

CREATE INDEX graph_rel_has_asset_identity IF NOT EXISTS
FOR ()-[rel:HAS_ASSET]-()
ON (rel.identity_key);

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

CREATE INDEX graph_rel_has_param_identity IF NOT EXISTS
FOR ()-[rel:HAS_PARAM]-()
ON (rel.identity_key);

CREATE INDEX graph_rel_has_request_shape_identity IF NOT EXISTS
FOR ()-[rel:HAS_REQUEST_SHAPE]-()
ON (rel.identity_key);

CREATE INDEX graph_rel_references_identity IF NOT EXISTS
FOR ()-[rel:REFERENCES]-()
ON (rel.identity_key);

CREATE INDEX graph_rel_has_tool_run_identity IF NOT EXISTS
FOR ()-[rel:HAS_TOOL_RUN]-()
ON (rel.identity_key);

CREATE INDEX graph_rel_has_action_outcome_identity IF NOT EXISTS
FOR ()-[rel:HAS_ACTION_OUTCOME]-()
ON (rel.identity_key);

CREATE INDEX graph_rel_outcome_of_run_identity IF NOT EXISTS
FOR ()-[rel:OUTCOME_OF_RUN]-()
ON (rel.identity_key);

CREATE INDEX graph_rel_used_capability_profile_identity IF NOT EXISTS
FOR ()-[rel:USED_CAPABILITY_PROFILE]-()
ON (rel.identity_key);

CREATE INDEX graph_rel_has_surface_fingerprint_feature_identity IF NOT EXISTS
FOR ()-[rel:HAS_SURFACE_FINGERPRINT_FEATURE]-()
ON (rel.identity_key);

CREATE INDEX graph_rel_has_outcome_feature_identity IF NOT EXISTS
FOR ()-[rel:HAS_OUTCOME_FEATURE]-()
ON (rel.identity_key);

CREATE INDEX graph_rel_before_surface_snapshot_identity IF NOT EXISTS
FOR ()-[rel:BEFORE_SURFACE_SNAPSHOT]-()
ON (rel.identity_key);

CREATE INDEX graph_rel_after_surface_snapshot_identity IF NOT EXISTS
FOR ()-[rel:AFTER_SURFACE_SNAPSHOT]-()
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

CREATE INDEX graph_rel_supported_by_identity IF NOT EXISTS
FOR ()-[rel:SUPPORTED_BY]-()
ON (rel.identity_key);

CREATE INDEX graph_rel_supports_evidence_identity IF NOT EXISTS
FOR ()-[rel:SUPPORTS_EVIDENCE]-()
ON (rel.identity_key);

CREATE INDEX graph_rel_derived_from_identity IF NOT EXISTS
FOR ()-[rel:DERIVED_FROM]-()
ON (rel.identity_key);
