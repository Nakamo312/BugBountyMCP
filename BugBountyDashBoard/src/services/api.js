import axios from 'axios'

const API_BASE_URL = '/api/v1'

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Health
export const healthCheck = () => api.get('/health')

// Programs
export const listPrograms = (limit = 100, offset = 0) => 
  api.get('/programs/', { params: { limit, offset } })

export const getProgram = (programId) => 
  api.get(`/programs/${programId}`)

export const getProgramBasic = (programId) => 
  api.get(`/programs/${programId}/basic`)

export const createProgram = (data) => 
  api.post('/programs/', data)

export const updateProgram = (programId, data) => 
  api.patch(`/programs/${programId}`, data)

export const deleteProgram = (programId) => 
  api.delete(`/programs/${programId}`)

export const updateProgramName = (programId, newName) => 
  api.patch(`/programs/${programId}/name`, null, { params: { new_name: newName } })

// Hosts
export const getHostsByProgram = (programId, params = {}) => 
  api.get(`/hosts/program/${programId}`, { params })

export const getHostWithEndpoints = (hostId) => 
  api.get(`/hosts/${hostId}`)

export const getHostWithServices = (hostId) => 
  api.get(`/hosts/${hostId}/services`)

export const getEndpointsByHost = (hostId, params = {}) => 
  api.get(`/hosts/${hostId}/endpoints`, { params })

export const getEndpointWithDetails = (endpointId) => 
  api.get(`/hosts/endpoints/${endpointId}`)

export const getEndpointFullDetails = (endpointId) => 
  api.get(`/hosts/endpoints/${endpointId}/full`)

export const getParametersByEndpoint = (endpointId, params = {}) => 
  api.get(`/hosts/endpoints/${endpointId}/parameters`, { params })

export const getHeadersByEndpoint = (endpointId, params = {}) => 
  api.get(`/hosts/endpoints/${endpointId}/headers`, { params })

export const getHostsWithStats = (programId, params = {}) => 
  api.get(`/hosts/program/${programId}/stats`, { params })

export const getProgramStats = (programId) => 
  api.get(`/hosts/program/${programId}/program-stats`)

export const getEndpointsWithBody = (programId, params = {}) => 
  api.get(`/hosts/program/${programId}/endpoints-with-body`, { params })

// Actions
export const listActionCatalog = () =>
  api.get('/actions/catalog')

export const getActionCatalogItem = (catalogId) =>
  api.get(`/actions/catalog/${catalogId}`)

export const listActions = (params = {}) =>
  api.get('/actions', { params })

export const listPendingApprovalActions = (params = {}) =>
  api.get('/actions/pending-approval', { params })

export const approveAction = (actionId, data = {}) =>
  api.post(`/actions/${actionId}/approve`, data)

export const rejectAction = (actionId, data = {}) =>
  api.post(`/actions/${actionId}/reject`, data)

export const cancelAction = (actionId, data = {}) =>
  api.post(`/actions/${actionId}/cancel`, data)

let actionCatalogCache = null

const resolveCatalogId = async (capability, profile) => {
  if (!actionCatalogCache) {
    const response = await listActionCatalog()
    actionCatalogCache = response.data?.items || []
  }
  const item = actionCatalogCache.find(
    (entry) => entry.capability === capability && entry.profile === profile,
  )
  if (!item) {
    throw new Error(`Action catalog entry not found: ${capability}/${profile}`)
  }
  return item.id
}

export const createAction = ({ catalog_id, program_id, targets, options = {}, requested_by = 'ui' }) =>
  api.post('/actions', {
    program_id,
    catalog_id,
    targets,
    options,
    requested_by,
  })

export const createCatalogAction = ({ catalog_id, program_id, targets, options = {}, requested_by = 'ui' }) =>
  createAction({
    catalog_id,
    program_id,
    targets,
    options,
    requested_by,
  })

const asAction = async (capability, profile, data, { targetField = 'targets' } = {}) => {
  const { program_id, [targetField]: targetValue, targets: ignoredTargets, ...options } = data
  const catalog_id = await resolveCatalogId(capability, profile)
  return createAction({
    catalog_id,
    program_id,
    targets: targetValue,
    options,
  })
}

export const runSubfinder = (data) =>
  asAction('subfinder', 'passive-recon', data)

export const runHTTPX = (data) =>
  asAction('httpx', 'safe-web-probe', data)

export const runGAU = (data) =>
  asAction('gau', 'archive-url-discovery', data)

export const runWaymore = (data) =>
  asAction('waymore', 'archive-url-discovery', data)

export const runKatana = (data) =>
  asAction('katana', 'safe-crawl', data)

export const runPlaywright = (data) =>
  asAction('playwright', 'browser-crawl', data)

export const runLinkFinder = (data) =>
  asAction('linkfinder', 'js-endpoint-extraction', data)

export const runMantra = (data) =>
  asAction('mantra', 'js-secret-analysis', data)

export const runFFUF = (data) =>
  asAction('ffuf', 'content-discovery-light', data)

export const runAmass = (data) =>
  asAction('amass', data.active ? 'active-enum' : 'passive-enum', data)

export const runDNSx = (data) =>
  asAction(data.mode === 'ptr' ? 'dnsx-ptr' : 'dnsx', data.mode === 'ptr' ? 'reverse-dns' : 'dns-validate', data)

export const runSubjack = (data) =>
  asAction('subjack', 'takeover-check', data)

export const runASNMap = (data) =>
  asAction('asnmap', 'asn-discovery', data)

export const runMapCIDR = async ({ program_id, cidrs, skip_base, skip_broadcast, shuffle, timeout }) => {
  const catalog_id = await resolveCatalogId('mapcidr', 'cidr-expand')
  return createAction({
    catalog_id,
    program_id,
    targets: cidrs,
    options: { skip_base, skip_broadcast, shuffle, timeout },
  })
}

export const runNaabu = (data) =>
  asAction('naabu', data.scan_mode === 'active' ? 'connect-top-100' : 'passive-ports', data)

export const getInjectionCandidates = (programId, params = {}) => 
  api.get(`/analysis/program/${programId}/injection-candidates`, { params })

export const getSSRFCandidates = (programId, params = {}) => 
  api.get(`/analysis/program/${programId}/ssrf-candidates`, { params })

export const getIDORCandidates = (programId, params = {}) => 
  api.get(`/analysis/program/${programId}/idor-candidates`, { params })

export const getFileUploadCandidates = (programId, params = {}) => 
  api.get(`/analysis/program/${programId}/file-upload-candidates`, { params })

export const getReflectedParameters = (programId, params = {}) => 
  api.get(`/analysis/program/${programId}/reflected-parameters`, { params })

export const getArjunCandidates = (programId, params = {}) => 
  api.get(`/analysis/program/${programId}/arjun-candidates`, { params })

export const getAdminDebugEndpoints = (programId, params = {}) => 
  api.get(`/analysis/program/${programId}/admin-debug-endpoints`, { params })

export const getCORSAnalysis = (programId, params = {}) => 
  api.get(`/analysis/program/${programId}/cors-analysis`, { params })

export const getSensitiveHeaders = (programId, params = {}) => 
  api.get(`/analysis/program/${programId}/sensitive-headers`, { params })

export const getHostTechnologies = (programId, params = {}) => 
  api.get(`/analysis/program/${programId}/technologies`, { params })

export const getSubdomainTakeoverCandidates = (programId, params = {}) => 
  api.get(`/analysis/program/${programId}/subdomain-takeover`, { params })

export const getAPIPatterns = (programId, params = {}) =>
  api.get(`/analysis/program/${programId}/api-patterns`, { params })


// Agent workroom
export const getCampaignWorkspace = (params = {}) =>
  api.get('/campaign-workspace', { params })

export const getAgentActivity = (params = {}) =>
  api.get('/agent-activity', { params })

export const createAgentTask = (data) =>
  api.post('/agent-tasks', data)

export const getAgentTaskDetail = (taskId, params = {}) =>
  api.get(`/agent-tasks/${taskId}/detail`, { params })

export const appendAgentTaskMessage = (taskId, data) =>
  api.post(`/agent-tasks/${taskId}/messages`, data)

export const acceptAgentActionProposal = (proposalId, data = {}) =>
  api.post(`/agent-action-proposals/${proposalId}/accept`, data)

export const rejectAgentActionProposal = (proposalId, data = {}) =>
  api.post(`/agent-action-proposals/${proposalId}/reject`, data)

export const suppressAgentActionProposal = (proposalId, data = {}) =>
  api.post(`/agent-action-proposals/${proposalId}/suppress`, data)

export const acceptActionExperienceProposal = (proposalId, data = {}) =>
  api.post(`/action-experience-proposals/${proposalId}/accept`, data)

export const retryAcceptActionExperienceProposal = (proposalId, data = {}) =>
  api.post(`/action-experience-proposals/${proposalId}/retry-accept`, data)

export const rejectActionExperienceProposal = (proposalId, data = {}) =>
  api.post(`/action-experience-proposals/${proposalId}/reject`, data)

export const suppressActionExperienceProposal = (proposalId, data = {}) =>
  api.post(`/action-experience-proposals/${proposalId}/suppress`, data)



// Workbench
export const getWorkbenchBootstrap = (programId) =>
  api.get('/workbench/bootstrap', { params: { program_id: programId } })

export const getWorkbenchGraph = ({ programId, lens = 'surface', seed, depth = 1, limit = 250 } = {}) => {
  const params = { program_id: programId, lens, depth, limit }
  if (seed) params.seed = seed
  return api.get('/workbench/graph', { params })
}

export const getWorkbenchEntity = (programId, entityKey) =>
  api.get(`/workbench/entities/${encodeURIComponent(entityKey)}`, { params: { program_id: programId } })

export const getWorkbenchEntityActions = (programId, entityKey) =>
  api.get(`/workbench/entities/${encodeURIComponent(entityKey)}/actions`, { params: { program_id: programId } })

export const getWorkbenchAvailableActions = ({ programId, entityKey, entity, lens, context = {} }) =>
  api.post('/workbench/actions/available', {
    program_id: programId,
    entity_key: entityKey,
    entity,
    context: { lens, ...context },
  })

export const submitWorkbenchAction = ({ programId, entityKey, catalogId, entity, targets, options = {}, lens, context = {} }) =>
  api.post('/workbench/actions/submit', {
    program_id: programId,
    entity_key: entityKey,
    catalog_id: catalogId,
    entity,
    targets,
    options,
    requested_by: 'workbench',
    context: { lens, ...context },
  })

export const getWorkbenchEntityMemory = (programId, entityKey) =>
  api.get(`/workbench/entities/${encodeURIComponent(entityKey)}/memory`, { params: { program_id: programId } })

export const retrieveWorkbenchEvidence = (data) =>
  api.post('/workbench/retrieve', data)

export const runWorkbenchProjectionRefresh = (data) =>
  api.post('/workbench/projections/run', data)

// Program projection overview
export const getProgramProjectionOverview = (programId) =>
  api.get('/program-projection-overview', { params: { program_id: programId } })

export const getProgramProjectionOperatorPlan = (programId) =>
  api.get('/program-projection-overview/plan', { params: { program_id: programId } })

// Surface component analysis
export const getSurfaceComponentAnalysis = ({ programId, snapshotId, previousSnapshotId } = {}) => {
  const params = { program_id: programId, snapshot_id: snapshotId }
  if (previousSnapshotId) params.previous_snapshot_id = previousSnapshotId
  return api.get('/surface-component-analysis', { params })
}

export const getLatestSurfaceComponentAnalysis = (programId) =>
  api.get('/surface-component-analysis/latest', { params: { program_id: programId } })

// Infrastructure

export default api
