import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, CheckCircle2, Loader2, Plus, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { errorMessage } from '../api/client'
import {
  connectorHealth,
  costSummary,
  createApiKey,
  createUser,
  deleteApiKey,
  listApiKeys,
  listConnectors,
  listModels,
  listScoringRules,
  listUsers,
  updateConnector,
  updateModel,
  updateScoringRule,
  updateUser,
} from '../api/endpoints'
import type { UserRole } from '../api/types'
import SpendControl from '../components/SpendControl'
import {
  Card,
  ErrorState,
  formatMoney,
  Loading,
  Modal,
  PageHeader,
  relativeTime,
  StatTile,
  Table,
  titleCase,
} from '../components/ui'

const TABS = ['Connectors', 'AI models', 'API keys', 'Scoring', 'Users', 'Cost'] as const
type Tab = (typeof TABS)[number]

const ROLES: UserRole[] = ['admin', 'researcher', 'sales_user', 'viewer']

export default function Admin() {
  const [tab, setTab] = useState<Tab>('Connectors')
  const queryClient = useQueryClient()

  const health = useQuery({ queryKey: ['connector-health'], queryFn: connectorHealth })
  const connectors = useQuery({ queryKey: ['connectors'], queryFn: listConnectors })
  const models = useQuery({ queryKey: ['models'], queryFn: listModels })
  const keys = useQuery({ queryKey: ['api-keys'], queryFn: listApiKeys })
  const rules = useQuery({ queryKey: ['scoring-rules'], queryFn: listScoringRules })
  const users = useQuery({ queryKey: ['users'], queryFn: listUsers })
  const costs = useQuery({ queryKey: ['costs'], queryFn: () => costSummary(30) })

  const [keyOpen, setKeyOpen] = useState(false)
  const [keyForm, setKeyForm] = useState({ provider_slug: 'anthropic', label: '', value: '' })
  const [userOpen, setUserOpen] = useState(false)
  const [userForm, setUserForm] = useState({
    email: '',
    full_name: '',
    password: '',
    role: 'sales_user' as UserRole,
  })
  const [error, setError] = useState<string | null>(null)

  const saveKey = useMutation({
    mutationFn: () => createApiKey(keyForm),
    onSuccess: () => {
      setKeyOpen(false)
      setKeyForm({ provider_slug: 'anthropic', label: '', value: '' })
      void queryClient.invalidateQueries({ queryKey: ['api-keys'] })
    },
    onError: (err) => setError(errorMessage(err)),
  })
  const removeKey = useMutation({
    mutationFn: (id: string) => deleteApiKey(id),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['api-keys'] }),
  })
  const saveUser = useMutation({
    mutationFn: () => createUser(userForm),
    onSuccess: () => {
      setUserOpen(false)
      setUserForm({ email: '', full_name: '', password: '', role: 'sales_user' })
      void queryClient.invalidateQueries({ queryKey: ['users'] })
    },
    onError: (err) => setError(errorMessage(err)),
  })
  const patchUser = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: Record<string, unknown> }) =>
      updateUser(id, payload),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['users'] }),
  })
  const patchConnector = useMutation({
    mutationFn: ({ slug, payload }: { slug: string; payload: Record<string, unknown> }) =>
      updateConnector(slug, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['connectors'] })
      void queryClient.invalidateQueries({ queryKey: ['connector-health'] })
    },
  })
  const patchModel = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: Record<string, unknown> }) =>
      updateModel(id, payload),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['models'] }),
  })
  const patchRule = useMutation({
    mutationFn: ({ component, weight }: { component: string; weight: number }) =>
      updateScoringRule(component, weight),
    onSuccess: () => {
      setError(null)
      void queryClient.invalidateQueries({ queryKey: ['scoring-rules'] })
    },
    onError: (err) => setError(errorMessage(err)),
  })

  const weightTotal = (rules.data ?? [])
    .filter((rule) => rule.is_active)
    .reduce((sum, rule) => sum + rule.weight, 0)

  return (
    <>
      <PageHeader
        title="Administration"
        subtitle="Data sources, AI providers, scoring weights, users and cost control."
      />

      <div className="mb-4 flex flex-wrap gap-1 border-b border-app">
        {TABS.map((name) => (
          <button
            key={name}
            className={
              tab === name
                ? 'border-b-2 border-brand-600 px-3.5 py-2 text-sm font-medium text-brand-600'
                : 'border-b-2 border-transparent px-3.5 py-2 text-sm text-muted hover:text-inherit'
            }
            onClick={() => setTab(name)}
          >
            {name}
          </button>
        ))}
      </div>

      {error && (
        <p className="mb-4 rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700 dark:bg-rose-500/10 dark:text-rose-300">
          {error}
        </p>
      )}

      {tab === 'Connectors' && (
        <div className="space-y-4">
          <Card title="Live connector health" description="What discovery can actually do right now">
            {health.isLoading ? (
              <Loading />
            ) : (
              <ul className="space-y-3">
                {(health.data ?? []).map((item) => (
                  <li key={item.slug} className="flex items-start gap-3">
                    {item.available ? (
                      <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-500" />
                    ) : (
                      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-500" />
                    )}
                    <div>
                      <p className="text-sm font-medium">{item.name}</p>
                      <p className="text-xs text-muted">{item.reason}</p>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card title="Connector settings" bodyClassName="p-0">
            <Table>
              <thead className="border-b border-app">
                <tr>
                  <th className="th">Connector</th>
                  <th className="th">Kind</th>
                  <th className="th">Cost / call</th>
                  <th className="th">Rate limit</th>
                  <th className="th">Enabled</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[rgb(var(--border))]">
                {(connectors.data ?? []).map((connector) => (
                  <tr key={connector.slug} className="row-hover">
                    <td className="td">
                      <p className="font-medium">{connector.name}</p>
                      <p className="max-w-md text-xs text-muted">{connector.notes}</p>
                    </td>
                    <td className="td text-sm">{titleCase(connector.kind)}</td>
                    <td className="td tabular-nums text-sm">
                      {formatMoney(connector.cost_per_call_usd, 4)}
                    </td>
                    <td className="td tabular-nums text-sm">{connector.rate_limit_per_minute}/min</td>
                    <td className="td">
                      <input
                        type="checkbox"
                        checked={connector.is_enabled}
                        onChange={(event) =>
                          patchConnector.mutate({
                            slug: connector.slug,
                            payload: { is_enabled: event.target.checked },
                          })
                        }
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </Card>
        </div>
      )}

      {tab === 'AI models' && (
        <div className="space-y-4">
        <SpendControl />
        <Card
          title="Models and pricing"
          description="Cheap models run on every company; the smart tier only on qualified prospects."
          bodyClassName="p-0"
        >
          <Table>
            <thead className="border-b border-app">
              <tr>
                <th className="th">Model</th>
                <th className="th">Tier</th>
                <th className="th">Input $/Mtok</th>
                <th className="th">Output $/Mtok</th>
                <th className="th">Enabled</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[rgb(var(--border))]">
              {(models.data ?? []).map((model) => (
                <tr key={model.model_id} className="row-hover">
                  <td className="td">
                    <p className="font-medium">{model.display_name}</p>
                    <p className="font-mono text-xs text-muted">{model.model_id}</p>
                  </td>
                  <td className="td">
                    <select
                      className="input py-1"
                      value={model.tier}
                      onChange={(event) =>
                        patchModel.mutate({
                          id: model.model_id,
                          payload: { tier: event.target.value },
                        })
                      }
                    >
                      <option value="cheap">cheap</option>
                      <option value="smart">smart</option>
                    </select>
                  </td>
                  <td className="td tabular-nums">{model.input_cost_per_mtok.toFixed(2)}</td>
                  <td className="td tabular-nums">{model.output_cost_per_mtok.toFixed(2)}</td>
                  <td className="td">
                    <input
                      type="checkbox"
                      checked={model.is_enabled}
                      onChange={(event) =>
                        patchModel.mutate({
                          id: model.model_id,
                          payload: { is_enabled: event.target.checked },
                        })
                      }
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </Table>
        </Card>
        </div>
      )}

      {tab === 'API keys' && (
        <Card
          title="Provider API keys"
          description="Encrypted at rest with Fernet. The raw value is never returned by the API."
          actions={
            <button className="btn-primary" onClick={() => setKeyOpen(true)}>
              <Plus className="h-4 w-4" />
              Add key
            </button>
          }
          bodyClassName="p-0"
        >
          {!keys.data?.length ? (
            <p className="px-5 py-6 text-sm text-muted">
              No keys stored. Discovery falls back to the keyless sources and reports fall back to
              the rules engine.
            </p>
          ) : (
            <Table>
              <thead className="border-b border-app">
                <tr>
                  <th className="th">Provider</th>
                  <th className="th">Label</th>
                  <th className="th">Key</th>
                  <th className="th">Added</th>
                  <th className="th" />
                </tr>
              </thead>
              <tbody className="divide-y divide-[rgb(var(--border))]">
                {keys.data.map((key) => (
                  <tr key={key.id} className="row-hover">
                    <td className="td font-medium">{key.provider_slug}</td>
                    <td className="td">{key.label}</td>
                    <td className="td font-mono text-sm">{key.masked_hint}</td>
                    <td className="td text-sm text-muted">{relativeTime(key.created_at)}</td>
                    <td className="td text-right">
                      <button
                        className="btn-ghost px-2 text-rose-600"
                        onClick={() => removeKey.mutate(key.id)}
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </Table>
          )}
        </Card>
      )}

      {tab === 'Scoring' && (
        <Card
          title="Opportunity scoring weights"
          description={`Active weights must total 100. Currently ${weightTotal.toFixed(1)}.`}
        >
          <div className="space-y-4">
            {(rules.data ?? []).map((rule) => (
              <div key={rule.id} className="flex flex-wrap items-center gap-4">
                <div className="min-w-[14rem] flex-1">
                  <p className="text-sm font-medium">{titleCase(rule.component)}</p>
                  <p className="text-xs text-muted">{rule.description}</p>
                </div>
                <input
                  className="input w-24"
                  type="number"
                  min={0}
                  max={100}
                  step="0.5"
                  defaultValue={rule.weight}
                  onBlur={(event) => {
                    const weight = Number(event.target.value)
                    if (weight !== rule.weight) {
                      patchRule.mutate({ component: rule.component, weight })
                    }
                  }}
                />
              </div>
            ))}
          </div>
          <p className="mt-4 border-t border-app pt-3 text-xs text-muted">
            A change that would break the 100-point total is rejected, so the score always stays on
            a 0–100 scale. Re-score a company from its detail page to apply new weights.
          </p>
        </Card>
      )}

      {tab === 'Users' && (
        <Card
          title="Users and roles"
          actions={
            <button className="btn-primary" onClick={() => setUserOpen(true)}>
              <Plus className="h-4 w-4" />
              Add user
            </button>
          }
          bodyClassName="p-0"
        >
          <Table>
            <thead className="border-b border-app">
              <tr>
                <th className="th">Name</th>
                <th className="th">Email</th>
                <th className="th">Role</th>
                <th className="th">Active</th>
                <th className="th">Last login</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[rgb(var(--border))]">
              {(users.data ?? []).map((user) => (
                <tr key={user.id} className="row-hover">
                  <td className="td font-medium">{user.full_name}</td>
                  <td className="td text-sm">{user.email}</td>
                  <td className="td">
                    <select
                      className="input py-1"
                      value={user.role}
                      onChange={(event) =>
                        patchUser.mutate({ id: user.id, payload: { role: event.target.value } })
                      }
                    >
                      {ROLES.map((role) => (
                        <option key={role} value={role}>
                          {titleCase(role)}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className="td">
                    <input
                      type="checkbox"
                      checked={user.is_active}
                      onChange={(event) =>
                        patchUser.mutate({
                          id: user.id,
                          payload: { is_active: event.target.checked },
                        })
                      }
                    />
                  </td>
                  <td className="td text-sm text-muted">{relativeTime(user.last_login_at)}</td>
                </tr>
              ))}
            </tbody>
          </Table>
        </Card>
      )}

      {tab === 'Cost' && (
        <div className="space-y-4">
          {costs.isLoading ? (
            <Loading />
          ) : costs.isError ? (
            <ErrorState message={errorMessage(costs.error)} />
          ) : (
            <>
              <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
                <StatTile label="Total (30d)" value={formatMoney(costs.data!.total_cost_usd, 4)} />
                <StatTile label="LLM spend" value={formatMoney(costs.data!.llm_cost_usd, 4)} />
                <StatTile label="Prospects produced" value={costs.data!.prospects_produced} />
                <StatTile
                  label="Cost per prospect"
                  value={formatMoney(costs.data!.cost_per_prospect_usd, 4)}
                />
              </div>
              <div className="grid gap-4 lg:grid-cols-2">
                <Card title="By model" bodyClassName="p-0">
                  <Table>
                    <thead className="border-b border-app">
                      <tr>
                        <th className="th">Model</th>
                        <th className="th">Cost</th>
                        <th className="th">Input tokens</th>
                        <th className="th">Output tokens</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[rgb(var(--border))]">
                      {costs.data!.by_model.map((row) => (
                        <tr key={String(row.model)} className="row-hover">
                          <td className="td font-mono text-sm">{String(row.model)}</td>
                          <td className="td tabular-nums">
                            {formatMoney(Number(row.cost_usd), 4)}
                          </td>
                          <td className="td tabular-nums">
                            {Number(row.input_tokens).toLocaleString()}
                          </td>
                          <td className="td tabular-nums">
                            {Number(row.output_tokens).toLocaleString()}
                          </td>
                        </tr>
                      ))}
                      {!costs.data!.by_model.length && (
                        <tr>
                          <td className="td text-muted" colSpan={4}>
                            No LLM usage recorded.
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </Table>
                </Card>
                <Card title="By agent" bodyClassName="p-0">
                  <Table>
                    <thead className="border-b border-app">
                      <tr>
                        <th className="th">Agent</th>
                        <th className="th">Cost</th>
                        <th className="th">Calls</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[rgb(var(--border))]">
                      {costs.data!.by_agent.map((row) => (
                        <tr key={String(row.agent)} className="row-hover">
                          <td className="td">{titleCase(String(row.agent))}</td>
                          <td className="td tabular-nums">
                            {formatMoney(Number(row.cost_usd), 4)}
                          </td>
                          <td className="td tabular-nums">{Number(row.calls)}</td>
                        </tr>
                      ))}
                      {!costs.data!.by_agent.length && (
                        <tr>
                          <td className="td text-muted" colSpan={3}>
                            No LLM usage recorded.
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </Table>
                </Card>
              </div>
            </>
          )}
        </div>
      )}

      <Modal
        open={keyOpen}
        onClose={() => setKeyOpen(false)}
        title="Add API key"
        footer={
          <>
            <button className="btn-secondary" onClick={() => setKeyOpen(false)}>
              Cancel
            </button>
            <button
              className="btn-primary"
              disabled={!keyForm.label || keyForm.value.length < 8 || saveKey.isPending}
              onClick={() => saveKey.mutate()}
            >
              {saveKey.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
              Save key
            </button>
          </>
        }
      >
        <div className="space-y-4">
          <div>
            <label className="label" htmlFor="provider">
              Provider
            </label>
            <select
              id="provider"
              className="input"
              value={keyForm.provider_slug}
              onChange={(event) => setKeyForm({ ...keyForm, provider_slug: event.target.value })}
            >
              <option value="anthropic">Anthropic (report synthesis)</option>
              <option value="serper">Serper (search discovery)</option>
              <option value="google_cse">Google Programmable Search</option>
            </select>
          </div>
          <div>
            <label className="label" htmlFor="label">
              Label
            </label>
            <input
              id="label"
              className="input"
              value={keyForm.label}
              onChange={(event) => setKeyForm({ ...keyForm, label: event.target.value })}
              placeholder="Production key"
            />
          </div>
          <div>
            <label className="label" htmlFor="value">
              Key
            </label>
            <input
              id="value"
              className="input font-mono"
              type="password"
              value={keyForm.value}
              onChange={(event) => setKeyForm({ ...keyForm, value: event.target.value })}
            />
            <p className="mt-1 text-xs text-muted">
              Stored encrypted. Only the first and last four characters are ever shown again.
            </p>
          </div>
        </div>
      </Modal>

      <Modal
        open={userOpen}
        onClose={() => setUserOpen(false)}
        title="Add user"
        footer={
          <>
            <button className="btn-secondary" onClick={() => setUserOpen(false)}>
              Cancel
            </button>
            <button
              className="btn-primary"
              disabled={saveUser.isPending || userForm.password.length < 10}
              onClick={() => saveUser.mutate()}
            >
              {saveUser.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
              Create user
            </button>
          </>
        }
      >
        <div className="space-y-4">
          <div>
            <label className="label" htmlFor="u-name">
              Full name
            </label>
            <input
              id="u-name"
              className="input"
              value={userForm.full_name}
              onChange={(event) => setUserForm({ ...userForm, full_name: event.target.value })}
            />
          </div>
          <div>
            <label className="label" htmlFor="u-email">
              Email
            </label>
            <input
              id="u-email"
              className="input"
              type="email"
              value={userForm.email}
              onChange={(event) => setUserForm({ ...userForm, email: event.target.value })}
            />
          </div>
          <div>
            <label className="label" htmlFor="u-password">
              Temporary password
            </label>
            <input
              id="u-password"
              className="input"
              type="password"
              value={userForm.password}
              onChange={(event) => setUserForm({ ...userForm, password: event.target.value })}
            />
            <p className="mt-1 text-xs text-muted">At least 10 characters.</p>
          </div>
          <div>
            <label className="label" htmlFor="u-role">
              Role
            </label>
            <select
              id="u-role"
              className="input"
              value={userForm.role}
              onChange={(event) => setUserForm({ ...userForm, role: event.target.value as UserRole })}
            >
              {ROLES.map((role) => (
                <option key={role} value={role}>
                  {titleCase(role)}
                </option>
              ))}
            </select>
          </div>
        </div>
      </Modal>
    </>
  )
}
