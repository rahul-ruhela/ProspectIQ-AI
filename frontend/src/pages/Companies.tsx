import { useQuery } from '@tanstack/react-query'
import { Building2, Download, Search, SlidersHorizontal } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { errorMessage } from '../api/client'
import { downloadExport, listCompanies, listCountries, listIndustries } from '../api/endpoints'
import type { ScoreCategory } from '../api/types'
import {
  Card,
  EmptyState,
  ErrorState,
  Pagination,
  PageHeader,
  relativeTime,
  ScoreBadge,
  SkeletonRows,
  Table,
  VerificationBadge,
} from '../components/ui'

interface Props {
  /** Prospects view = qualified only, sorted by score. */
  qualifiedOnly?: boolean
  title?: string
  subtitle?: string
}

const CATEGORIES: Array<ScoreCategory | ''> = [
  '',
  'exceptional',
  'high_priority',
  'medium',
  'low',
  'poor',
]

export default function Companies({ qualifiedOnly = false, title, subtitle }: Props) {
  const [page, setPage] = useState(1)
  const [q, setQ] = useState('')
  const [country, setCountry] = useState('')
  const [industry, setIndustry] = useState('')
  const [category, setCategory] = useState<ScoreCategory | ''>('')
  const [includeRejected, setIncludeRejected] = useState(false)
  const [showFilters, setShowFilters] = useState(false)
  const [downloading, setDownloading] = useState(false)

  const countries = useQuery({ queryKey: ['countries'], queryFn: listCountries })
  const industries = useQuery({ queryKey: ['industries'], queryFn: listIndustries })

  const params = {
    page,
    page_size: 25,
    ...(q.trim() ? { q: q.trim() } : {}),
    ...(country ? { country_code: country } : {}),
    ...(industry ? { industry_slug: industry } : {}),
    ...(category ? { category } : {}),
    ...(qualifiedOnly ? { min_score: 60 } : {}),
    include_rejected: qualifiedOnly ? false : includeRejected,
    sort_by: 'opportunity_score',
    sort_dir: 'desc',
  }

  const query = useQuery({
    queryKey: ['companies', params],
    queryFn: () => listCompanies(params),
  })

  async function onExport() {
    setDownloading(true)
    try {
      const blob = await downloadExport({
        ...(qualifiedOnly ? { min_score: 60 } : { min_score: 0 }),
        include_rejected: includeRejected,
      })
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `prospectiq-export-${new Date().toISOString().slice(0, 10)}.csv`
      link.click()
      URL.revokeObjectURL(url)
    } finally {
      setDownloading(false)
    }
  }

  return (
    <>
      <PageHeader
        title={title ?? 'Companies'}
        subtitle={
          subtitle ??
          'Every company the department researched, with its source and verification state.'
        }
        actions={
          <>
            <button className="btn-secondary" onClick={() => setShowFilters((v) => !v)}>
              <SlidersHorizontal className="h-4 w-4" />
              Filters
            </button>
            <button className="btn-secondary" onClick={onExport} disabled={downloading}>
              <Download className="h-4 w-4" />
              Export CSV
            </button>
          </>
        }
      />

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="relative min-w-[16rem] flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
          <input
            className="input pl-9"
            placeholder="Search by name, domain or description…"
            value={q}
            onChange={(event) => {
              setQ(event.target.value)
              setPage(1)
            }}
          />
        </div>
      </div>

      {showFilters && (
        <Card className="mb-4">
          <div className="grid gap-4 md:grid-cols-4">
            <div>
              <label className="label" htmlFor="country">
                Country
              </label>
              <select
                id="country"
                className="input"
                value={country}
                onChange={(event) => {
                  setCountry(event.target.value)
                  setPage(1)
                }}
              >
                <option value="">All countries</option>
                {(countries.data ?? []).map((c) => (
                  <option key={c.iso2} value={c.iso2}>
                    {c.name}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="label" htmlFor="industry">
                Industry
              </label>
              <select
                id="industry"
                className="input"
                value={industry}
                onChange={(event) => {
                  setIndustry(event.target.value)
                  setPage(1)
                }}
              >
                <option value="">All industries</option>
                {(industries.data ?? []).map((i) => (
                  <option key={i.slug} value={i.slug}>
                    {i.name}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="label" htmlFor="category">
                Opportunity tier
              </label>
              <select
                id="category"
                className="input"
                value={category}
                onChange={(event) => {
                  setCategory(event.target.value as ScoreCategory | '')
                  setPage(1)
                }}
              >
                {CATEGORIES.map((value) => (
                  <option key={value} value={value}>
                    {value === '' ? 'All tiers' : value.replace('_', ' ')}
                  </option>
                ))}
              </select>
            </div>
            {!qualifiedOnly && (
              <div className="flex items-end">
                <label className="flex cursor-pointer items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={includeRejected}
                    onChange={(event) => {
                      setIncludeRejected(event.target.checked)
                      setPage(1)
                    }}
                  />
                  Show rejected companies
                </label>
              </div>
            )}
          </div>
        </Card>
      )}

      <Card bodyClassName="p-0">
        {query.isLoading ? (
          <SkeletonRows rows={8} cols={7} />
        ) : query.isError ? (
          <ErrorState message={errorMessage(query.error)} onRetry={() => void query.refetch()} />
        ) : !query.data?.items.length ? (
          <EmptyState
            title="No companies match"
            message="Run a research job, or widen your filters."
            icon={<Building2 className="h-8 w-8" />}
            action={
              <Link className="btn-primary" to="/campaigns">
                Go to campaigns
              </Link>
            }
          />
        ) : (
          <>
            <Table>
              <thead className="border-b border-app">
                <tr>
                  <th className="th">Company</th>
                  <th className="th">Location</th>
                  <th className="th">Industry</th>
                  <th className="th">Opportunity</th>
                  <th className="th">Data</th>
                  <th className="th">Verification</th>
                  <th className="th">Researched</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[rgb(var(--border))]">
                {query.data.items.map((company) => (
                  <tr key={company.id} className="row-hover">
                    <td className="td">
                      <Link
                        className="font-medium hover:text-brand-600"
                        to={`/companies/${company.id}`}
                      >
                        {company.name}
                      </Link>
                      <p className="text-xs text-muted">{company.domain ?? 'No domain'}</p>
                      {company.is_rejected && (
                        <span className="badge mt-1 bg-rose-50 text-rose-700 ring-rose-600/20 dark:bg-rose-500/10 dark:text-rose-300">
                          Rejected
                        </span>
                      )}
                    </td>
                    <td className="td text-sm">
                      {company.city ?? '—'}
                      {company.country_code ? `, ${company.country_code}` : ''}
                    </td>
                    <td className="td text-sm capitalize">
                      {company.industry_slug?.replace(/_/g, ' ') ?? '—'}
                    </td>
                    <td className="td">
                      <ScoreBadge
                        score={company.opportunity_score}
                        category={company.opportunity_category}
                      />
                    </td>
                    <td className="td">
                      <div className="flex items-center gap-2">
                        <span className="h-1.5 w-16 overflow-hidden rounded-full surface-muted">
                          <span
                            className="block h-full rounded-full bg-brand-500"
                            style={{ width: `${company.data_completeness * 100}%` }}
                          />
                        </span>
                        <span className="text-xs tabular-nums text-muted">
                          {Math.round(company.data_completeness * 100)}%
                        </span>
                      </div>
                    </td>
                    <td className="td">
                      <VerificationBadge status={company.verification_status} />
                    </td>
                    <td className="td text-sm text-muted">
                      {relativeTime(company.last_researched_at)}
                    </td>
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
    </>
  )
}
