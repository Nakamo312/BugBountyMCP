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

export const getEndpointsByHost = (hostId, params = {}) => 
  api.get(`/hosts/${hostId}/endpoints`, { params })

export const getEndpointWithDetails = (endpointId) => 
  api.get(`/hosts/endpoints/${endpointId}`)

export const getParametersByEndpoint = (endpointId, params = {}) => 
  api.get(`/hosts/endpoints/${endpointId}/parameters`, { params })

export const getHeadersByEndpoint = (endpointId, params = {}) => 
  api.get(`/hosts/endpoints/${endpointId}/headers`, { params })

// Scans
export const scanSubfinder = (data) => 
  api.post('/scan/subfinder', data)

export const scanHTTPX = (data) => 
  api.post('/scan/httpx', data)

export const scanGAU = (data) => 
  api.post('/scan/gau', data)

export const scanWaymore = (data) => 
  api.post('/scan/waymore', data)

export const scanKatana = (data) => 
  api.post('/scan/katana', data)

export const scanPlaywright = (data) => 
  api.post('/scan/playwright', data)

export const scanLinkFinder = (data) => 
  api.post('/scan/linkfinder', data)

export const scanMantra = (data) => 
  api.post('/scan/mantra', data)

export const scanFFUF = (data) => 
  api.post('/scan/ffuf', data)

export const scanDNSx = (data) => 
  api.post('/scan/dnsx', data)

export const scanSubjack = (data) => 
  api.post('/scan/subjack', data)

export const scanASNMap = (data) => 
  api.post('/scan/asnmap', data)

export const scanMapCIDR = (data) => 
  api.post('/scan/mapcidr', data)

export const scanNaabu = (data) => 
  api.post('/scan/naabu', data)

export default api
