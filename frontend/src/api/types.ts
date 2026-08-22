/** Types mirroring the backend Pydantic schemas. */

export type UserRole = 'admin' | 'researcher' | 'sales_user' | 'viewer'

export type VerificationStatus =
  | 'verified'
  | 'needs_verification'
  | 'unknown'
  | 'rejected'

export type Certainty = 'observed' | 'likely' | 'possible' | 'unknown'

export type ScoreCategory =
  | 'exceptional'
  | 'high_priority'
  | 'medium'
  | 'low'
  | 'poor'

export type CampaignStatus = 'draft' | 'active' | 'paused' | 'completed' | 'archived'

export type JobStatus =
  | 'queued'
  | 'running'
  | 'paused'
  | 'completed'
  | 'failed'
  | 'cancelled'

export type TaskStatus =
  | 'pending'
  | 'assigned'
  | 'running'
  | 'waiting'
  | 'completed'
  | 'failed'
  | 'skipped'
  | 'cancelled'

export type AgentStatus =
  | 'idle'
  | 'running'
  | 'processing'
  | 'waiting'
  | 'completed'
  | 'failed'
  | 'disabled'

export type PipelineStage =
  | 'discovered'
  | 'researching'
  | 'qualified'
  | 'ready_contact'
  | 'contacted'
  | 'reply_received'
  | 'meeting'
  | 'proposal'
  | 'negotiation'
  | 'customer'
  | 'lost'

export type ContactStatusValue =
  | 'not_contacted'
  | 'called'
  | 'contacted'
  | 'follow_up_required'
  | 'meeting_scheduled'
  | 'not_interested'
  | 'converted'

export interface User {
  id: string
  email: string
  full_name: string
  role: UserRole
  is_active: boolean
  organization_id: string | null
  last_login_at: string | null
  created_at: string
}

export interface TokenPair {
  access_token: string
  refresh_token: string
  token_type: string
  expires_in: number
}

export interface AuthResponse {
  user: User
  tokens: TokenPair
}

export interface Page<T> {
  items: T[]
  total: number
  page: number
  page_size: number
  pages: number
}

export interface CampaignFilters {
  countries: string[]
  regions: string[]
  cities: string[]
  industries: string[]
  business_types: string[]
  keywords: string[]
  exclude_keywords: string[]
  employee_min: number | null
  employee_max: number | null
  min_opportunity_score: number
  require_website: boolean
}

export interface Campaign {
  id: string
  name: string
  objective: string | null
  status: CampaignStatus
  target_prospect_count: number
  budget_usd: number
  spent_usd: number
  offered_services: string[]
  strategy: Record<string, unknown> | null
  filters: (CampaignFilters & { id: string }) | null
  created_at: string
  updated_at: string
}

export interface CampaignStats {
  campaign_id: string
  companies: number
  qualified: number
  ready_to_contact: number
  avg_opportunity_score: number
  total_cost_usd: number
  cost_per_prospect_usd: number
}

export interface ResearchJob {
  id: string
  campaign_id: string
  status: JobStatus
  progress_percent: number
  current_stage: string | null
  plan: Record<string, any> | null
  companies_discovered: number
  companies_verified: number
  companies_rejected: number
  prospects_qualified: number
  cost_usd: number
  error: string | null
  started_at: string | null
  finished_at: string | null
  created_at: string
}

export interface Technology {
  id: string
  slug: string
  name: string
  category: string
  version: string | null
  matched_signature: string | null
  source: string | null
  source_url: string | null
  confidence: number
  verification_status: VerificationStatus
  last_verified_at: string | null
}

export interface WebsiteFeature {
  id: string
  feature_key: string
  present: boolean | null
  certainty: Certainty
  detail: string | null
  source_url: string | null
  confidence: number
}

export interface WebsitePage {
  id: string
  url: string
  page_type: string
  http_status: number | null
  title: string | null
  word_count: number
  forms_count: number
  fetched_at: string | null
}

export interface Website {
  id: string
  url: string
  final_url: string | null
  http_status: number | null
  is_reachable: boolean | null
  is_https: boolean | null
  title: string | null
  meta_description: string | null
  pages_crawled: number
  load_time_ms: number | null
  is_mobile_friendly: boolean | null
  copyright_year: number | null
  quality_score: number | null
  crawled_at: string | null
  features: WebsiteFeature[]
  pages: WebsitePage[]
}

export interface EmailVerification {
  syntax_valid: boolean
  domain_resolves: boolean | null
  has_mx: boolean | null
  is_disposable: boolean | null
  is_free_provider: boolean | null
  is_role_account: boolean | null
  quality: string
  status: VerificationStatus
  confidence: number
  checked_at: string | null
}

export interface PhoneVerification {
  e164: string | null
  country_code: string | null
  dial_code: string | null
  line_type: string
  is_valid: boolean
  whatsapp_likely: boolean | null
  status: VerificationStatus
  confidence: number
  checked_at: string | null
}

export interface Contact {
  id: string
  contact_type: 'email' | 'phone'
  value: string
  label: string | null
  is_primary: boolean
  found_on_url: string | null
  source: string | null
  source_url: string | null
  confidence: number
  verification_status: VerificationStatus
  last_verified_at: string | null
  email_verification: EmailVerification | null
  phone_verification: PhoneVerification | null
}

export interface DecisionMaker {
  id: string
  full_name: string
  role_title: string | null
  role_category: string | null
  seniority: string | null
  profile_url: string | null
  linkedin_url: string | null
  source: string | null
  source_url: string | null
  confidence: number
  verification_status: VerificationStatus
  contacts: Contact[]
}

export interface BuyingSignal {
  id: string
  signal_type: string
  title: string
  detail: string | null
  certainty: Certainty
  strength: number
  source_url: string | null
  confidence: number
  observed_at: string | null
}

export interface ScoreComponent {
  normalised: number
  weight: number
  points: number
  reasons: string[]
}

export interface OpportunityScore {
  total: number
  category: ScoreCategory
  industry_fit: number
  company_size: number
  website_opportunity: number
  lead_opportunity: number
  ai_fit: number
  technology_readiness: number
  buying_signals: number
  service_match: number
  data_confidence: number
  breakdown: Record<string, ScoreComponent> | null
  recommended_services: string[]
}

export interface Evidence {
  id: string
  kind: string
  url: string | null
  excerpt: string | null
  observed_at: string | null
}

export interface ResearchFinding {
  id: string
  category: string
  statement: string
  certainty: Certainty
  impact: string | null
  confidence: number
  source_url: string | null
  evidence: Evidence[]
}

export interface AIResearch {
  id: string
  summary: string | null
  what_they_do: string | null
  how_they_acquire_customers: string | null
  problems: Array<Record<string, any>>
  opportunities: Array<Record<string, any>>
  recommended_services: string[]
  why_contact_them: string | null
  talking_points: string[]
  objections: string[]
  email_draft_subject: string | null
  email_draft_body: string | null
  call_script: string | null
  approved_at: string | null
  generated_by_model: string | null
  overall_confidence: number
  findings: ResearchFinding[]
}

export interface CompanySource {
  id: string
  source_type: string
  title: string | null
  snippet: string | null
  source_url: string | null
  confidence: number
}

export interface CompanyListItem {
  id: string
  name: string
  domain: string | null
  website: string | null
  industry_slug: string | null
  country_code: string | null
  city: string | null
  employee_count: number | null
  opportunity_score: number | null
  opportunity_category: ScoreCategory | null
  lead_quality_score: number | null
  data_completeness: number
  verification_status: VerificationStatus
  is_rejected: boolean
  last_researched_at: string | null
  created_at: string
}

export interface CompanyDetail extends CompanyListItem {
  legal_name: string | null
  description: string | null
  category: string | null
  business_type: string | null
  employee_range: string | null
  founded_year: number | null
  region: string | null
  address: string | null
  postal_code: string | null
  phone: string | null
  primary_email: string | null
  linkedin_url: string | null
  website_active: boolean | null
  rejection_reason: string | null
  confidence: number
  source: string | null
  source_url: string | null
  sources: CompanySource[]
  website_record: Website | null
  technologies: Technology[]
  contacts: Contact[]
  decision_makers: DecisionMaker[]
  signals: BuyingSignal[]
  score: OpportunityScore | null
  research: AIResearch | null
}

export interface Agent {
  id: string
  key: string
  display_name: string
  role: string
  goal: string
  tools: string[]
  model_tier: string
  status: AgentStatus
  is_enabled: boolean
  total_runs: number
  total_failures: number
  avg_confidence: number
  avg_duration_ms: number
  last_run_at: string | null
}

export interface AgentDetail extends Agent {
  input_schema: Record<string, any> | null
  output_schema: Record<string, any> | null
}

export interface DepartmentStatus {
  agents: Agent[]
  running_tasks: number
  pending_tasks: number
  failed_tasks_24h: number
  active_jobs: number
  tasks_by_status: Record<string, number>
}

export interface AgentTask {
  id: string
  agent_key: string
  research_job_id: string | null
  company_id: string | null
  sequence: number
  status: TaskStatus
  priority: number
  confidence: number | null
  attempts: number
  max_attempts: number
  error: string | null
  started_at: string | null
  finished_at: string | null
  created_at: string
}

export interface AgentLog {
  id: string
  agent_key: string
  level: string
  message: string
  context: Record<string, any> | null
  company_id: string | null
  created_at: string
}

export interface PipelineCard {
  id: string
  company_id: string
  stage: PipelineStage
  contact_status: ContactStatusValue
  assigned_user_id: string | null
  last_contact_at: string | null
  last_action: string | null
  next_follow_up_at: string | null
  contact_attempts: number
  deal_value_usd: number | null
  lost_reason: string | null
  notes: string | null
  updated_at: string
  company_name: string
  company_domain: string | null
  country_code: string | null
  opportunity_score: number | null
  assigned_user_name: string | null
}

export interface PipelineBoard {
  stages: Record<string, PipelineCard[]>
  counts: Record<string, number>
  total_value_usd: number
}

export interface Activity {
  id: string
  company_id: string | null
  user_id: string | null
  activity_type: string
  title: string
  body: string | null
  occurred_at: string | null
  created_at: string
}

export interface DashboardMetrics {
  companies_total: number
  companies_new_7d: number
  qualified_total: number
  ready_to_contact: number
  contacted_total: number
  customers_total: number
  avg_opportunity_score: number
  active_jobs: number
  agents_running: number
  spend_30d_usd: number
  cost_per_prospect_usd: number
  follow_ups_due: number
}

export interface TimeseriesPoint {
  date: string
  value: number
}

export interface AnalyticsOverview {
  discovery_trend: TimeseriesPoint[]
  score_distribution: Record<string, number>
  top_industries: Array<Record<string, string | number>>
  top_countries: Array<Record<string, string | number>>
  top_technologies: Array<Record<string, string | number>>
  pipeline_funnel: Array<{ stage: string; count: number }>
  cost_trend: TimeseriesPoint[]
  agent_performance: Array<Record<string, string | number>>
}

export interface Country {
  id: string
  iso2: string
  iso3: string
  name: string
  continent: string
  phone_code: string | null
  is_supported: boolean
}

export interface Industry {
  id: string
  slug: string
  name: string
  naics_code: string | null
  ai_fit_baseline: number
  is_active: boolean
}

export interface ServiceCatalogItem {
  id: string
  slug: string
  name: string
  description: string | null
  typical_deal_usd: number
  trigger_features: string[]
  is_active: boolean
}

export interface ConnectorHealth {
  slug: string
  name: string
  available: boolean
  reason: string
}

export interface Connector {
  id: string
  slug: string
  name: string
  kind: string
  requires_api_key: boolean
  is_enabled: boolean
  rate_limit_per_minute: number
  cost_per_call_usd: number
  notes: string | null
}

export interface AIModel {
  id: string
  provider_slug: string
  model_id: string
  display_name: string
  tier: string
  input_cost_per_mtok: number
  output_cost_per_mtok: number
  max_output_tokens: number
  is_enabled: boolean
}

export interface ApiKey {
  id: string
  provider_slug: string
  label: string
  masked_hint: string
  is_active: boolean
  last_used_at: string | null
  created_at: string
}

export interface ScoringRule {
  id: string
  component: string
  weight: number
  description: string | null
  is_active: boolean
}

export interface CostSummary {
  period_days: number
  llm_cost_usd: number
  connector_cost_usd: number
  total_cost_usd: number
  prospects_produced: number
  cost_per_prospect_usd: number
  by_model: Array<Record<string, string | number>>
  by_agent: Array<Record<string, string | number>>
}

export interface SystemStatus {
  version: string
  environment: string
  llm: { available: boolean; cheap_model: string; smart_model: string; note: string | null }
  discovery_connectors: ConnectorHealth[]
  discovery_available: boolean
  playwright_rendering: boolean
  respect_robots_txt: boolean
}

export interface SpendPolicy {
  allow_paid: boolean
  daily_limit_usd: number
  monthly_limit_usd: number
  alert_threshold_pct: number
}

export interface SpendStatus {
  policy: SpendPolicy
  spent_today_usd: number
  spent_month_usd: number
  daily_used_pct: number
  monthly_used_pct: number
  daily_remaining_usd: number
  monthly_remaining_usd: number
  paid_available: boolean
  blocked_reason: string | null
  alerting: boolean
  free_chain: string[]
  paid_chain: string[]
}
