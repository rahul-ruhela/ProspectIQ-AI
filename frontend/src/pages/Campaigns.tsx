import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Loader2, Plus, Search, Target } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { errorMessage } from '../api/client'
import {
  createCampaign,
  listCampaigns,
  listCountries,
  listIndustries,
  listServices,
} from '../api/endpoints'
import {
  Card,
  EmptyState,
  ErrorState,
  formatMoney,
  Modal,
  Pagination,
  PageHeader,
  relativeTime,
  SkeletonRows,
  StatusBadge,
  Table,
} from '../components/ui'
import { useAuth } from '../store/auth'

function MultiSelect({
  label,
  options,
  selected,
  onChange,
  placeholder,
}: {
  label: string
  options: Array<{ value: string; label: string; hint?: string }>
  selected: string[]
  onChange: (values: string[]) => void
  placeholder?: string
}) {
  const [term, setTerm] = useState('')
  const filtered = useMemo(() => {
    const needle = term.trim().toLowerCase()
    if (!needle) return options.slice(0, 60)
    return options.filter((o) => o.label.toLowerCase().includes(needle)).slice(0, 60)
  }, [options, term])

  const toggle = (value: string) =>
    onChange(selected.includes(value) ? selected.filter((v) => v !== value) : [...selected, value])

  return (
    <div>
      <label className="label">
        {label}
        {selected.length > 0 && <span className="ml-1 text-muted">({selected.length})</span>}
      </label>
      <div className="relative">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
        <input
          className="input pl-9"
          placeholder={placeholder ?? 'Search…'}
          value={term}
          onChange={(event) => setTerm(event.target.value)}
        />
      </div>
      {selected.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {selected.map((value) => {
            const option = options.find((o) => o.value === value)
            return (
              <button
                type="button"
                key={value}
                className="badge bg-brand-50 text-brand-700 ring-brand-600/20 dark:bg-brand-500/10 dark:text-brand-300"
                onClick={() => toggle(value)}
              >
                {option?.label ?? value} ×
              </button>
            )
          })}
        </div>
      )}
      <div className="mt-2 max-h-40 overflow-y-auto rounded-lg border border-app">
        {filtered.map((option) => (
          <label
            key={option.value}
            className="flex cursor-pointer items-center gap-2 px-3 py-1.5 text-sm row-hover"
          >
            <input
              type="checkbox"
              checked={selected.includes(option.value)}
              onChange={() => toggle(option.value)}
            />
            <span className="flex-1 truncate">{option.label}</span>
            {option.hint && <span className="text-xs text-muted">{option.hint}</span>}
          </label>
        ))}
        {!filtered.length && <p className="px-3 py-3 text-sm text-muted">No matches.</p>}
      </div>
    </div>
  )
}

function CreateCampaignModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const queryClient = useQueryClient()
  const countries = useQuery({ queryKey: ['countries'], queryFn: listCountries })
  const industries = useQuery({ queryKey: ['industries'], queryFn: listIndustries })
  const services = useQuery({ queryKey: ['services'], queryFn: listServices })

  const [form, setForm] = useState({
    name: '',
    objective: '',
    target_prospect_count: 25,
    budget_usd: 10,
  })
  const [selectedCountries, setSelectedCountries] = useState<string[]>([])
  const [selectedIndustries, setSelectedIndustries] = useState<string[]>([])
  const [selectedServices, setSelectedServices] = useState<string[]>([])
  const [cities, setCities] = useState('')
  const [minScore, setMinScore] = useState(40)
  // Off by default: a registered business with no website is the highest-value
  // prospect for the services being sold, so it must not be filtered out.
  const [requireWebsite, setRequireWebsite] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const mutation = useMutation({
    mutationFn: () =>
      createCampaign({
        name: form.name,
        objective: form.objective || null,
        target_prospect_count: Number(form.target_prospect_count),
        budget_usd: Number(form.budget_usd),
        offered_services: selectedServices,
        filters: {
          countries: selectedCountries,
          industries: selectedIndustries,
          cities: cities
            .split(',')
            .map((c) => c.trim())
            .filter(Boolean),
          min_opportunity_score: minScore,
          require_website: requireWebsite,
        },
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['campaigns'] })
      onClose()
      setForm({ name: '', objective: '', target_prospect_count: 25, budget_usd: 10 })
      setSelectedCountries([])
      setSelectedIndustries([])
      setSelectedServices([])
      setCities('')
    },
    onError: (err) => setError(errorMessage(err, 'Could not create the campaign.')),
  })

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="New campaign"
      wide
      footer={
        <>
          <button className="btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button
            className="btn-primary"
            disabled={!form.name || !selectedCountries.length || mutation.isPending}
            onClick={() => {
              setError(null)
              mutation.mutate()
            }}
          >
            {mutation.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
            Create campaign
          </button>
        </>
      }
    >
      <div className="space-y-5">
        <div>
          <label className="label" htmlFor="campaign-name">
            Campaign name
          </label>
          <input
            id="campaign-name"
            className="input"
            value={form.name}
            onChange={(event) => setForm({ ...form, name: event.target.value })}
            placeholder="HVAC automation — North America"
          />
        </div>

        <div>
          <label className="label" htmlFor="objective">
            What are you looking for?
          </label>
          <textarea
            id="objective"
            className="input min-h-[80px]"
            value={form.objective}
            onChange={(event) => setForm({ ...form, objective: event.target.value })}
            placeholder="Find small HVAC businesses in the USA and Canada that need AI automation."
          />
          <p className="mt-1 text-xs text-muted">
            The CEO orchestrator reads this to build the research strategy. Your filters below
            always take precedence over anything it infers.
          </p>
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          <MultiSelect
            label="Countries"
            placeholder="Search countries…"
            options={(countries.data ?? []).map((c) => ({
              value: c.iso2,
              label: c.name,
              hint: c.continent,
            }))}
            selected={selectedCountries}
            onChange={setSelectedCountries}
          />
          <MultiSelect
            label="Industries"
            placeholder="Search industries…"
            options={(industries.data ?? []).map((i) => ({
              value: i.slug,
              label: i.name,
              hint: `AI fit ${i.ai_fit_baseline.toFixed(2)}`,
            }))}
            selected={selectedIndustries}
            onChange={setSelectedIndustries}
          />
        </div>

        <div>
          <label className="label" htmlFor="cities">
            Cities (optional, comma separated)
          </label>
          <input
            id="cities"
            className="input"
            value={cities}
            onChange={(event) => setCities(event.target.value)}
            placeholder="Austin, Dallas, Houston"
          />
          <p className="mt-1 text-xs text-muted">
            Naming cities lets the mapped-business connector run, which returns structured records
            with website, phone and address.
          </p>
        </div>

        <MultiSelect
          label="Services you want to sell"
          placeholder="Search services…"
          options={(services.data ?? []).map((s) => ({
            value: s.slug,
            label: s.name,
            hint: formatMoney(s.typical_deal_usd, 0),
          }))}
          selected={selectedServices}
          onChange={setSelectedServices}
        />

        <div className="grid gap-4 sm:grid-cols-3">
          <div>
            <label className="label" htmlFor="target">
              Target prospects
            </label>
            <input
              id="target"
              className="input"
              type="number"
              min={1}
              max={1000}
              value={form.target_prospect_count}
              onChange={(event) =>
                setForm({ ...form, target_prospect_count: Number(event.target.value) })
              }
            />
          </div>
          <div>
            <label className="label" htmlFor="budget">
              Budget (USD)
            </label>
            <input
              id="budget"
              className="input"
              type="number"
              min={0}
              step="0.5"
              value={form.budget_usd}
              onChange={(event) => setForm({ ...form, budget_usd: Number(event.target.value) })}
            />
          </div>
          <div>
            <label className="label" htmlFor="minscore">
              Minimum score
            </label>
            <input
              id="minscore"
              className="input"
              type="number"
              min={0}
              max={100}
              value={minScore}
              onChange={(event) => setMinScore(Number(event.target.value))}
            />
          </div>
        </div>

        <label className="flex items-start gap-3 rounded-lg border border-slate-200 px-3 py-3 dark:border-slate-700">
          <input
            type="checkbox"
            className="mt-0.5"
            checked={requireWebsite}
            onChange={(event) => setRequireWebsite(event.target.checked)}
          />
          <span className="text-sm">
            <span className="font-medium">Only keep businesses that have a website</span>
            <span className="block text-slate-500 dark:text-slate-400">
              Leave this off to include registered businesses found on Google Maps and
              OpenStreetMap that have no website at all — usually the strongest prospects
              for a web or automation offer.
            </span>
          </span>
        </label>

        {error && (
          <p className="rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700 dark:bg-rose-500/10 dark:text-rose-300">
            {error}
          </p>
        )}
      </div>
    </Modal>
  )
}

export default function Campaigns() {
  const { can } = useAuth()
  const [page, setPage] = useState(1)
  const [creating, setCreating] = useState(false)
  const pageSize = 20

  const query = useQuery({
    queryKey: ['campaigns', page],
    queryFn: () => listCampaigns({ page, page_size: pageSize }),
  })

  return (
    <>
      <PageHeader
        title="Campaigns"
        subtitle="A campaign defines who to look for. Starting research hands it to the CEO orchestrator."
        actions={
          can('researcher') && (
            <button className="btn-primary" onClick={() => setCreating(true)}>
              <Plus className="h-4 w-4" />
              New campaign
            </button>
          )
        }
      />

      <Card bodyClassName="p-0">
        {query.isLoading ? (
          <SkeletonRows rows={6} cols={6} />
        ) : query.isError ? (
          <ErrorState message={errorMessage(query.error)} onRetry={() => void query.refetch()} />
        ) : !query.data?.items.length ? (
          <EmptyState
            title="No campaigns yet"
            message="Describe who you want to sell to, and the AI department will go find them."
            icon={<Target className="h-8 w-8" />}
            action={
              can('researcher') && (
                <button className="btn-primary" onClick={() => setCreating(true)}>
                  <Plus className="h-4 w-4" />
                  Create your first campaign
                </button>
              )
            }
          />
        ) : (
          <>
            <Table>
              <thead className="border-b border-app">
                <tr>
                  <th className="th">Campaign</th>
                  <th className="th">Status</th>
                  <th className="th">Targeting</th>
                  <th className="th">Target</th>
                  <th className="th">Budget</th>
                  <th className="th">Created</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[rgb(var(--border))]">
                {query.data.items.map((campaign) => (
                  <tr key={campaign.id} className="row-hover">
                    <td className="td">
                      <Link className="font-medium hover:text-brand-600" to={`/campaigns/${campaign.id}`}>
                        {campaign.name}
                      </Link>
                      {campaign.objective && (
                        <p className="mt-0.5 max-w-md truncate text-xs text-muted">
                          {campaign.objective}
                        </p>
                      )}
                    </td>
                    <td className="td">
                      <StatusBadge status={campaign.status} />
                    </td>
                    <td className="td text-sm text-muted">
                      {campaign.filters?.countries.join(', ') || '—'}
                      {campaign.filters?.industries.length
                        ? ` · ${campaign.filters.industries.length} industries`
                        : ''}
                    </td>
                    <td className="td tabular-nums">{campaign.target_prospect_count}</td>
                    <td className="td tabular-nums">
                      {formatMoney(campaign.spent_usd, 3)}
                      <span className="text-muted"> / {formatMoney(campaign.budget_usd, 2)}</span>
                    </td>
                    <td className="td text-sm text-muted">{relativeTime(campaign.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </Table>
            <Pagination
              page={query.data.page}
              pages={query.data.pages}
              total={query.data.total}
              pageSize={query.data.page_size}
              onChange={setPage}
            />
          </>
        )}
      </Card>

      <CreateCampaignModal open={creating} onClose={() => setCreating(false)} />
    </>
  )
}
