/** Typed wrappers for every backend endpoint the UI uses. */
import api from './client'
import type {
  Activity,
  Agent,
  AgentDetail,
  AgentLog,
  AgentTask,
  AIModel,
  AIResearch,
  AnalyticsOverview,
  ApiKey,
  AuthResponse,
  Campaign,
  CampaignFilters,
  CampaignStats,
  CompanyDetail,
  CompanyListItem,
  Connector,
  ConnectorHealth,
  CostSummary,
  Country,
  DashboardMetrics,
  DepartmentStatus,
  Industry,
  Page,
  PipelineBoard,
  PipelineCard,
  ResearchJob,
  ScoringRule,
  ServiceCatalogItem,
  SystemStatus,
  User,
  SpendPolicy,
  SpendStatus,
} from './types'

// --- auth ---
export const login = (email: string, password: string) =>
  api.post<AuthResponse>('/auth/login', { email, password }).then((r) => r.data)

export const register = (payload: {
  email: string
  password: string
  full_name: string
  organization_name: string
}) => api.post<AuthResponse>('/auth/register', payload).then((r) => r.data)

export const me = () => api.get<User>('/auth/me').then((r) => r.data)

export const changePassword = (current_password: string, new_password: string) =>
  api.post('/auth/change-password', { current_password, new_password }).then((r) => r.data)

// --- users ---
export const listUsers = () => api.get<User[]>('/users').then((r) => r.data)
export const createUser = (payload: {
  email: string
  password: string
  full_name: string
  role: string
}) => api.post<User>('/users', payload).then((r) => r.data)
export const updateUser = (id: string, payload: Record<string, unknown>) =>
  api.patch<User>(`/users/${id}`, payload).then((r) => r.data)

// --- reference ---
export const listCountries = () =>
  api.get<Country[]>('/reference/countries').then((r) => r.data)
export const listIndustries = () =>
  api.get<Industry[]>('/reference/industries').then((r) => r.data)
export const listServices = () =>
  api.get<ServiceCatalogItem[]>('/reference/services').then((r) => r.data)
/** `/system/status` sits outside the versioned prefix, so it is called on the API root. */
export const systemStatus = () => {
  const root = (api.defaults.baseURL ?? '').replace(/\/api\/v1\/?$/, '')
  return api.get<SystemStatus>(`${root}/system/status`).then((r) => r.data)
}

// --- campaigns ---
export const listCampaigns = (params?: Record<string, unknown>) =>
  api.get<Page<Campaign>>('/campaigns', { params }).then((r) => r.data)
export const getCampaign = (id: string) =>
  api.get<Campaign>(`/campaigns/${id}`).then((r) => r.data)
export const createCampaign = (payload: {
  name: string
  objective?: string | null
  target_prospect_count: number
  budget_usd: number
  offered_services: string[]
  filters: Partial<CampaignFilters>
}) => api.post<Campaign>('/campaigns', payload).then((r) => r.data)
export const updateCampaign = (id: string, payload: Record<string, unknown>) =>
  api.patch<Campaign>(`/campaigns/${id}`, payload).then((r) => r.data)
export const archiveCampaign = (id: string) =>
  api.delete(`/campaigns/${id}`).then((r) => r.data)
export const campaignStats = (id: string) =>
  api.get<CampaignStats>(`/campaigns/${id}/stats`).then((r) => r.data)
export const startResearch = (id: string, payload: { max_companies?: number; run_inline?: boolean }) =>
  api.post<ResearchJob>(`/campaigns/${id}/start`, payload).then((r) => r.data)

// --- research jobs ---
export const listJobs = (params?: Record<string, unknown>) =>
  api.get<Page<ResearchJob>>('/jobs', { params }).then((r) => r.data)
export const getJob = (id: string) => api.get<ResearchJob>(`/jobs/${id}`).then((r) => r.data)
export const cancelJob = (id: string) =>
  api.post<ResearchJob>(`/jobs/${id}/cancel`).then((r) => r.data)
export const pauseJob = (id: string) =>
  api.post<ResearchJob>(`/jobs/${id}/pause`).then((r) => r.data)
export const resumeJob = (id: string) =>
  api.post<ResearchJob>(`/jobs/${id}/resume`).then((r) => r.data)

// --- companies ---
export const listCompanies = (params?: Record<string, unknown>) =>
  api.get<Page<CompanyListItem>>('/companies', { params }).then((r) => r.data)
export const getCompany = (id: string) =>
  api.get<CompanyDetail>(`/companies/${id}`).then((r) => r.data)
export const getReport = (id: string) =>
  api.get<AIResearch>(`/companies/${id}/report`).then((r) => r.data)
export const approveReport = (id: string, approved: boolean, note?: string) =>
  api.post<AIResearch>(`/companies/${id}/report/approve`, { approved, note }).then((r) => r.data)
export const rejectCompany = (id: string, reason: string) =>
  api.post(`/companies/${id}/reject`, null, { params: { reason } }).then((r) => r.data)
export const rescoreCompany = (id: string) =>
  api.post(`/companies/${id}/rescore`).then((r) => r.data)
export const exportCompaniesUrl = (params: Record<string, unknown>) => ({
  path: '/companies/export',
  params,
})
export const downloadExport = async (params: Record<string, unknown>) => {
  const response = await api.get('/companies/export', { params, responseType: 'blob' })
  return response.data as Blob
}

// --- agents ---
export const listAgents = () => api.get<Agent[]>('/agents').then((r) => r.data)
export const getAgent = (key: string) =>
  api.get<AgentDetail>(`/agents/${key}`).then((r) => r.data)
export const departmentStatus = () =>
  api.get<DepartmentStatus>('/agents/status').then((r) => r.data)
export const toggleAgent = (key: string, is_enabled: boolean) =>
  api.post<Agent>(`/agents/${key}/toggle`, { is_enabled }).then((r) => r.data)
export const listAgentTasks = (params?: Record<string, unknown>) =>
  api.get<Page<AgentTask>>('/agents/tasks', { params }).then((r) => r.data)
export const listAgentLogs = (params?: Record<string, unknown>) =>
  api.get<AgentLog[]>('/agents/logs', { params }).then((r) => r.data)

// --- crm ---
export const getPipeline = (params?: Record<string, unknown>) =>
  api.get<PipelineBoard>('/crm/pipeline', { params }).then((r) => r.data)
export const changeStage = (companyId: string, payload: Record<string, unknown>) =>
  api.post<PipelineCard>(`/crm/${companyId}/stage`, payload).then((r) => r.data)
export const setContactStatus = (companyId: string, payload: Record<string, unknown>) =>
  api.post<PipelineCard>(`/crm/${companyId}/contact-status`, payload).then((r) => r.data)
export const assignProspect = (companyId: string, assigned_user_id: string | null) =>
  api.post<PipelineCard>(`/crm/${companyId}/assign`, { assigned_user_id }).then((r) => r.data)
export const listActivities = (companyId: string) =>
  api.get<Activity[]>(`/crm/${companyId}/activities`).then((r) => r.data)
export const createActivity = (companyId: string, payload: Record<string, unknown>) =>
  api.post<Activity>(`/crm/${companyId}/activities`, payload).then((r) => r.data)
export const listFollowUps = (params?: Record<string, unknown>) =>
  api.get<PipelineCard[]>('/crm/follow-ups', { params }).then((r) => r.data)
export const submitFeedback = (payload: Record<string, unknown>) =>
  api.post('/crm/feedback', payload).then((r) => r.data)

// --- analytics ---
export const dashboardMetrics = () =>
  api.get<DashboardMetrics>('/analytics/dashboard').then((r) => r.data)
export const analyticsOverview = (days = 30) =>
  api.get<AnalyticsOverview>('/analytics/overview', { params: { days } }).then((r) => r.data)

// --- admin ---
export const listModels = () => api.get<AIModel[]>('/admin/models').then((r) => r.data)
export const updateModel = (modelId: string, payload: Record<string, unknown>) =>
  api.patch<AIModel>(`/admin/models/${modelId}`, payload).then((r) => r.data)
export const listApiKeys = () => api.get<ApiKey[]>('/admin/api-keys').then((r) => r.data)
export const createApiKey = (payload: { provider_slug: string; label: string; value: string }) =>
  api.post<ApiKey>('/admin/api-keys', payload).then((r) => r.data)
export const deleteApiKey = (id: string) =>
  api.delete(`/admin/api-keys/${id}`).then((r) => r.data)
export const listConnectors = () =>
  api.get<Connector[]>('/admin/connectors').then((r) => r.data)
export const connectorHealth = () =>
  api.get<ConnectorHealth[]>('/admin/connectors/health').then((r) => r.data)
export const updateConnector = (slug: string, payload: Record<string, unknown>) =>
  api.patch<Connector>(`/admin/connectors/${slug}`, payload).then((r) => r.data)
export const listScoringRules = () =>
  api.get<ScoringRule[]>('/admin/scoring-rules').then((r) => r.data)
export const updateScoringRule = (component: string, weight: number) =>
  api.patch<ScoringRule[]>(`/admin/scoring-rules/${component}`, { weight }).then((r) => r.data)
export const getSpendPolicy = () =>
  api.get<SpendStatus>('/admin/spend-policy').then((r) => r.data)
export const updateSpendPolicy = (payload: Partial<SpendPolicy>) =>
  api.put<SpendStatus>('/admin/spend-policy', payload).then((r) => r.data)
export const spendStatus = () =>
  api.get<SpendStatus>('/admin/spend-status').then((r) => r.data)
export const costSummary = (days = 30) =>
  api.get<CostSummary>('/admin/costs', { params: { days } }).then((r) => r.data)
