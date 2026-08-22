import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ArrowLeft,
  Check,
  Copy,
  ExternalLink,
  Globe,
  Loader2,
  Mail,
  Phone,
  RefreshCw,
  ShieldCheck,
  User,
  X,
} from 'lucide-react'
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { errorMessage } from '../api/client'
import {
  approveReport,
  getCompany,
  listActivities,
  rescoreCompany,
  setContactStatus,
} from '../api/endpoints'
import type { ContactStatusValue } from '../api/types'
import {
  Card,
  CertaintyBadge,
  ConfidenceMeter,
  EmptyState,
  ErrorState,
  Loading,
  Modal,
  PageHeader,
  Provenance,
  relativeTime,
  ScoreBadge,
  titleCase,
  ValueOrUnknown,
  VerificationBadge,
  formatDateTime,
} from '../components/ui'
import { useAuth } from '../store/auth'

const TABS = [
  'Overview',
  'Report',
  'Website',
  'People & Contacts',
  'Signals',
  'Score',
  'Evidence',
  'Activity',
] as const
type Tab = (typeof TABS)[number]

const CONTACT_STATUSES: ContactStatusValue[] = [
  'not_contacted',
  'called',
  'contacted',
  'follow_up_required',
  'meeting_scheduled',
  'not_interested',
  'converted',
]

function CopyButton({ value }: { value: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <button
      className="btn-ghost px-1.5 py-1"
      title="Copy"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(value)
          setCopied(true)
          setTimeout(() => setCopied(false), 1500)
        } catch {
          /* clipboard can be blocked; the value is selectable on screen anyway */
        }
      }}
    >
      {copied ? <Check className="h-3.5 w-3.5 text-emerald-500" /> : <Copy className="h-3.5 w-3.5" />}
    </button>
  )
}

export default function CompanyDetail() {
  const { id = '' } = useParams()
  const queryClient = useQueryClient()
  const { can } = useAuth()
  const [tab, setTab] = useState<Tab>('Overview')
  const [logOpen, setLogOpen] = useState(false)
  const [logStatus, setLogStatus] = useState<ContactStatusValue>('called')
  const [logNote, setLogNote] = useState('')

  const company = useQuery({ queryKey: ['company', id], queryFn: () => getCompany(id) })
  const activities = useQuery({
    queryKey: ['activities', id],
    queryFn: () => listActivities(id),
  })

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['company', id] })
    void queryClient.invalidateQueries({ queryKey: ['activities', id] })
  }

  const approve = useMutation({
    mutationFn: (approved: boolean) => approveReport(id, approved),
    onSuccess: invalidate,
  })
  const rescore = useMutation({ mutationFn: () => rescoreCompany(id), onSuccess: invalidate })
  const logContact = useMutation({
    mutationFn: () =>
      setContactStatus(id, { contact_status: logStatus, note: logNote || undefined }),
    onSuccess: () => {
      setLogOpen(false)
      setLogNote('')
      invalidate()
    },
  })

  if (company.isLoading) return <Loading />
  if (company.isError) {
    return <ErrorState message={errorMessage(company.error)} onRetry={() => void company.refetch()} />
  }

  const c = company.data!
  const website = c.website_record
  const report = c.research
  const emails = c.contacts.filter((contact) => contact.contact_type === 'email')
  const phones = c.contacts.filter((contact) => contact.contact_type === 'phone')
  const missingFeatures = (website?.features ?? []).filter((f) => f.present === false)
  const presentFeatures = (website?.features ?? []).filter((f) => f.present === true)

  return (
    <>
      <Link className="btn-ghost mb-3 -ml-2 text-sm" to="/companies">
        <ArrowLeft className="h-4 w-4" />
        All companies
      </Link>

      <PageHeader
        title={c.name}
        subtitle={
          <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
            {c.website && (
              <a
                className="inline-flex items-center gap-1 hover:text-brand-600"
                href={c.website}
                target="_blank"
                rel="noreferrer noopener"
              >
                <Globe className="h-3.5 w-3.5" />
                {c.domain}
                <ExternalLink className="h-3 w-3" />
              </a>
            )}
            <span>
              {c.city ?? 'Unknown city'}
              {c.country_code ? `, ${c.country_code}` : ''}
            </span>
            <span className="capitalize">{c.industry_slug?.replace(/_/g, ' ') ?? 'Unknown industry'}</span>
            <VerificationBadge status={c.verification_status} />
          </span>
        }
        actions={
          <>
            {can('sales_user') && (
              <button className="btn-secondary" onClick={() => setLogOpen(true)}>
                <Phone className="h-4 w-4" />
                Log outreach
              </button>
            )}
            {can('researcher') && (
              <button className="btn-secondary" onClick={() => rescore.mutate()} disabled={rescore.isPending}>
                {rescore.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <RefreshCw className="h-4 w-4" />
                )}
                Re-score
              </button>
            )}
            {can('sales_user') && report && (
              <button
                className={report.approved_at ? 'btn-secondary' : 'btn-primary'}
                onClick={() => approve.mutate(!report.approved_at)}
                disabled={approve.isPending}
              >
                {approve.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : report.approved_at ? (
                  <X className="h-4 w-4" />
                ) : (
                  <ShieldCheck className="h-4 w-4" />
                )}
                {report.approved_at ? 'Withdraw approval' : 'Approve for outreach'}
              </button>
            )}
          </>
        }
      />

      {c.is_rejected && (
        <div className="card mb-6 border-rose-300 bg-rose-50 p-4 text-sm dark:border-rose-500/30 dark:bg-rose-500/10">
          <p className="font-medium text-rose-800 dark:text-rose-200">
            This company was rejected by the quality gate.
          </p>
          <p className="mt-1 text-rose-700 dark:text-rose-300">{c.rejection_reason}</p>
        </div>
      )}

      <div className="mb-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <div className="card p-5">
          <p className="text-sm text-muted">Opportunity score</p>
          <div className="mt-2">
            <ScoreBadge score={c.opportunity_score} category={c.opportunity_category} />
          </div>
        </div>
        <div className="card p-5">
          <p className="text-sm text-muted">Data completeness</p>
          <p className="mt-2 text-2xl font-semibold tabular-nums">
            {Math.round(c.data_completeness * 100)}%
          </p>
        </div>
        <div className="card p-5">
          <p className="text-sm text-muted">Source confidence</p>
          <div className="mt-3">
            <ConfidenceMeter value={c.confidence} />
          </div>
        </div>
        <div className="card p-5">
          <p className="text-sm text-muted">Human approval</p>
          <p className="mt-2 text-sm">
            {report?.approved_at ? (
              <span className="badge bg-emerald-50 text-emerald-700 ring-emerald-600/20 dark:bg-emerald-500/10 dark:text-emerald-300">
                <ShieldCheck className="h-3 w-3" />
                Approved {relativeTime(report.approved_at)}
              </span>
            ) : (
              <span className="text-muted">Not approved — nothing will be sent.</span>
            )}
          </p>
        </div>
      </div>

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

      {tab === 'Overview' && (
        <div className="grid gap-4 lg:grid-cols-3">
          <Card className="lg:col-span-2" title="What we know">
            <dl className="grid gap-4 sm:grid-cols-2">
              {[
                ['Legal name', c.legal_name],
                ['Category', c.category],
                ['Business type', c.business_type],
                ['Employees', c.employee_count],
                ['Founded', c.founded_year],
                ['Address', c.address],
                ['Region', c.region],
                ['Postal code', c.postal_code],
                ['Primary email', c.primary_email],
                ['Phone', c.phone],
              ].map(([label, value]) => (
                <div key={label as string}>
                  <dt className="text-sm text-muted">{label}</dt>
                  <dd className="text-sm">
                    <ValueOrUnknown value={value as never} />
                  </dd>
                </div>
              ))}
            </dl>
            {c.description && (
              <div className="mt-5 border-t border-app pt-4">
                <p className="text-sm text-muted">Description as published</p>
                <p className="mt-1 text-sm">{c.description}</p>
              </div>
            )}
          </Card>

          <Card title="Where this came from" description="Independent sources raise confidence">
            {!c.sources.length ? (
              <p className="text-sm text-muted">No sources recorded.</p>
            ) : (
              <ul className="space-y-3">
                {c.sources.map((source) => (
                  <li key={source.id} className="border-b border-app pb-3 last:border-0 last:pb-0">
                    <p className="text-sm font-medium">{titleCase(source.source_type)}</p>
                    {source.title && <p className="text-sm">{source.title}</p>}
                    <div className="mt-1">
                      <Provenance sourceUrl={source.source_url} confidence={source.confidence} />
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card className="lg:col-span-3" title="Technology detected" description="Each match stores the exact signature that proved it">
            {!c.technologies.length ? (
              <p className="text-sm text-muted">
                No technology could be fingerprinted from the pages we fetched.
              </p>
            ) : (
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {c.technologies.map((tech) => (
                  <div key={tech.id} className="rounded-lg border border-app p-3">
                    <div className="flex items-center justify-between gap-2">
                      <p className="font-medium">{tech.name}</p>
                      <span className="badge surface-muted text-muted ring-transparent">
                        {titleCase(tech.category)}
                      </span>
                    </div>
                    {tech.matched_signature && (
                      <p className="mt-1 truncate font-mono text-xs text-muted" title={tech.matched_signature}>
                        {tech.matched_signature}
                      </p>
                    )}
                    <div className="mt-2">
                      <Provenance
                        source={tech.source}
                        sourceUrl={tech.source_url}
                        confidence={tech.confidence}
                        verifiedAt={tech.last_verified_at}
                      />
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </div>
      )}

      {tab === 'Report' && (
        <div className="grid gap-4 lg:grid-cols-3">
          {!report ? (
            <div className="lg:col-span-3">
              <Card>
                <EmptyState
                  title="No report yet"
                  message="Reports are generated for companies that clear the quality gate and score above the campaign threshold."
                />
              </Card>
            </div>
          ) : (
            <>
              <Card className="lg:col-span-2" title="Sales intelligence report">
                <div className="space-y-5 text-sm">
                  <section>
                    <h3 className="font-semibold">Who they are</h3>
                    <p className="mt-1">
                      <ValueOrUnknown value={report.summary} />
                    </p>
                  </section>
                  <section>
                    <h3 className="font-semibold">What they do</h3>
                    <p className="mt-1">
                      <ValueOrUnknown value={report.what_they_do} />
                    </p>
                  </section>
                  <section>
                    <h3 className="font-semibold">How they acquire customers</h3>
                    <p className="mt-1">
                      <ValueOrUnknown value={report.how_they_acquire_customers} />
                    </p>
                  </section>
                  <section>
                    <h3 className="font-semibold">Why contact them</h3>
                    <p className="mt-1">
                      <ValueOrUnknown value={report.why_contact_them} />
                    </p>
                  </section>
                  {report.talking_points.length > 0 && (
                    <section>
                      <h3 className="font-semibold">Talking points</h3>
                      <ul className="mt-1 list-disc space-y-1 pl-5">
                        {report.talking_points.map((point, index) => (
                          <li key={index}>{point}</li>
                        ))}
                      </ul>
                    </section>
                  )}
                  {report.objections.length > 0 && (
                    <section>
                      <h3 className="font-semibold">Likely objections</h3>
                      <ul className="mt-1 list-disc space-y-1 pl-5">
                        {report.objections.map((objection, index) => (
                          <li key={index}>{objection}</li>
                        ))}
                      </ul>
                    </section>
                  )}
                </div>
                <p className="mt-6 border-t border-app pt-3 text-xs text-muted">
                  Generated by {report.generated_by_model ?? 'rules engine'} · overall confidence{' '}
                  {Math.round(report.overall_confidence * 100)}%
                </p>
              </Card>

              <div className="space-y-4">
                <Card title="Email draft" description="Never sent automatically">
                  <p className="text-xs text-muted">Subject</p>
                  <p className="mb-3 font-medium">
                    <ValueOrUnknown value={report.email_draft_subject} />
                  </p>
                  <p className="text-xs text-muted">Body</p>
                  <pre className="mt-1 whitespace-pre-wrap rounded-lg surface-muted p-3 text-sm font-sans">
                    {report.email_draft_body ?? 'No draft generated.'}
                  </pre>
                  {report.email_draft_body && (
                    <div className="mt-2 flex justify-end">
                      <CopyButton value={report.email_draft_body} />
                    </div>
                  )}
                </Card>
                <Card title="Call opening">
                  <pre className="whitespace-pre-wrap rounded-lg surface-muted p-3 text-sm font-sans">
                    {report.call_script ?? 'No script generated.'}
                  </pre>
                </Card>
                <Card title="Recommended services">
                  {report.recommended_services.length ? (
                    <ul className="space-y-1.5 text-sm">
                      {report.recommended_services.map((service) => (
                        <li key={service} className="flex items-center gap-2">
                          <Check className="h-4 w-4 text-emerald-500" />
                          {titleCase(service)}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-sm text-muted">No specific service fit identified.</p>
                  )}
                </Card>
              </div>
            </>
          )}
        </div>
      )}

      {tab === 'Website' && (
        <div className="grid gap-4 lg:grid-cols-3">
          {!website ? (
            <div className="lg:col-span-3">
              <Card>
                <EmptyState title="No website analysis" message="This company has not been crawled." />
              </Card>
            </div>
          ) : (
            <>
              <Card title="Website health">
                <dl className="space-y-3 text-sm">
                  {[
                    ['Reachable', website.is_reachable ? 'Yes' : 'No'],
                    ['HTTPS', website.is_https ? 'Yes' : 'No'],
                    ['Mobile viewport', website.is_mobile_friendly ? 'Yes' : 'No'],
                    ['Quality score', website.quality_score !== null ? `${website.quality_score}/100` : null],
                    ['Load time', website.load_time_ms ? `${website.load_time_ms} ms` : null],
                    ['Copyright year', website.copyright_year],
                    ['Pages crawled', website.pages_crawled],
                    ['Crawled', formatDateTime(website.crawled_at)],
                  ].map(([label, value]) => (
                    <div key={label as string} className="flex justify-between gap-3">
                      <dt className="text-muted">{label}</dt>
                      <dd>
                        <ValueOrUnknown value={value as never} />
                      </dd>
                    </div>
                  ))}
                </dl>
              </Card>

              <Card className="lg:col-span-2" title="Capability gaps" description="Absence is the sellable finding">
                {!missingFeatures.length ? (
                  <p className="text-sm text-muted">Nothing material missing.</p>
                ) : (
                  <ul className="space-y-3">
                    {missingFeatures.map((feature) => (
                      <li key={feature.id} className="border-b border-app pb-3 last:border-0 last:pb-0">
                        <div className="flex items-center justify-between gap-2">
                          <p className="font-medium">{titleCase(feature.feature_key)}</p>
                          <CertaintyBadge certainty={feature.certainty} />
                        </div>
                        <p className="mt-0.5 text-sm text-muted">{feature.detail}</p>
                      </li>
                    ))}
                  </ul>
                )}
              </Card>

              <Card title="Present capabilities">
                {!presentFeatures.length ? (
                  <p className="text-sm text-muted">None detected.</p>
                ) : (
                  <div className="flex flex-wrap gap-1.5">
                    {presentFeatures.map((feature) => (
                      <span
                        key={feature.id}
                        className="badge bg-emerald-50 text-emerald-700 ring-emerald-600/20 dark:bg-emerald-500/10 dark:text-emerald-300"
                        title={feature.detail ?? undefined}
                      >
                        {titleCase(feature.feature_key)}
                      </span>
                    ))}
                  </div>
                )}
              </Card>

              <Card className="lg:col-span-2" title="Pages fetched" bodyClassName="p-0">
                <ul className="max-h-80 divide-y divide-[rgb(var(--border))] overflow-y-auto">
                  {website.pages.map((page) => (
                    <li key={page.id} className="flex items-center gap-3 px-5 py-2.5">
                      <span className="badge surface-muted text-muted ring-transparent shrink-0">
                        {titleCase(page.page_type)}
                      </span>
                      <a
                        className="min-w-0 flex-1 truncate text-sm hover:text-brand-600"
                        href={page.url}
                        target="_blank"
                        rel="noreferrer noopener"
                      >
                        {page.url}
                      </a>
                      <span className="shrink-0 text-xs tabular-nums text-muted">
                        {page.word_count} words · {page.forms_count} forms
                      </span>
                    </li>
                  ))}
                </ul>
              </Card>
            </>
          )}
        </div>
      )}

      {tab === 'People & Contacts' && (
        <div className="grid gap-4 lg:grid-cols-2">
          <Card title="Decision makers" description="Only people actually named on their own pages">
            {!c.decision_makers.length ? (
              <EmptyState
                title="Unknown"
                message="No decision maker is named on this company's public pages. A human must establish this before outreach — the platform will not guess a name."
                icon={<User className="h-8 w-8" />}
              />
            ) : (
              <ul className="space-y-4">
                {c.decision_makers.map((person) => (
                  <li key={person.id} className="border-b border-app pb-4 last:border-0 last:pb-0">
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <p className="font-medium">{person.full_name}</p>
                        <p className="text-sm text-muted">
                          <ValueOrUnknown value={person.role_title} />
                        </p>
                      </div>
                      <VerificationBadge status={person.verification_status} />
                    </div>
                    {person.linkedin_url && (
                      <a
                        className="mt-1 inline-flex items-center gap-1 text-xs text-brand-600 hover:underline"
                        href={person.linkedin_url}
                        target="_blank"
                        rel="noreferrer noopener"
                      >
                        LinkedIn <ExternalLink className="h-3 w-3" />
                      </a>
                    )}
                    <div className="mt-2">
                      <Provenance
                        source={person.source}
                        sourceUrl={person.source_url}
                        confidence={person.confidence}
                      />
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <div className="space-y-4">
            <Card title="Email addresses">
              {!emails.length ? (
                <p className="text-sm text-muted">No email address was published on the site.</p>
              ) : (
                <ul className="space-y-3">
                  {emails.map((contact) => (
                    <li key={contact.id} className="border-b border-app pb-3 last:border-0 last:pb-0">
                      <div className="flex items-center gap-2">
                        <Mail className="h-4 w-4 shrink-0 text-muted" />
                        <span className="min-w-0 flex-1 truncate font-mono text-sm">
                          {contact.value}
                        </span>
                        <CopyButton value={contact.value} />
                        <VerificationBadge status={contact.verification_status} />
                      </div>
                      {contact.email_verification && (
                        <p className="mt-1 text-xs text-muted">
                          {titleCase(contact.email_verification.quality)} ·{' '}
                          {contact.email_verification.has_mx ? 'MX records found' : 'No MX records'}
                          {contact.email_verification.is_disposable ? ' · disposable' : ''}
                        </p>
                      )}
                      <div className="mt-1">
                        <Provenance
                          source={contact.source}
                          sourceUrl={contact.source_url}
                          confidence={contact.confidence}
                        />
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </Card>

            <Card title="Phone numbers">
              {!phones.length ? (
                <p className="text-sm text-muted">No phone number was published on the site.</p>
              ) : (
                <ul className="space-y-3">
                  {phones.map((contact) => (
                    <li key={contact.id} className="border-b border-app pb-3 last:border-0 last:pb-0">
                      <div className="flex items-center gap-2">
                        <Phone className="h-4 w-4 shrink-0 text-muted" />
                        <span className="min-w-0 flex-1 truncate font-mono text-sm">
                          {contact.phone_verification?.e164 ?? contact.value}
                        </span>
                        <CopyButton value={contact.phone_verification?.e164 ?? contact.value} />
                        <VerificationBadge status={contact.verification_status} />
                      </div>
                      {contact.phone_verification && (
                        <p className="mt-1 text-xs text-muted">
                          {titleCase(contact.phone_verification.line_type)}
                          {contact.phone_verification.country_code
                            ? ` · ${contact.phone_verification.country_code}`
                            : ''}
                          {contact.phone_verification.whatsapp_likely ? ' · WhatsApp likely' : ''}
                        </p>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </div>
        </div>
      )}

      {tab === 'Signals' && (
        <Card title="Buying signals" description="Evidence the company is moving right now">
          {!c.signals.length ? (
            <EmptyState title="No buying signals observed" />
          ) : (
            <ul className="space-y-4">
              {c.signals.map((signal) => (
                <li key={signal.id} className="border-b border-app pb-4 last:border-0 last:pb-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="badge surface-muted text-muted ring-transparent">
                      {titleCase(signal.signal_type)}
                    </span>
                    <p className="font-medium">{signal.title}</p>
                    <CertaintyBadge certainty={signal.certainty} />
                  </div>
                  {signal.detail && <p className="mt-1 text-sm text-muted">{signal.detail}</p>}
                  <div className="mt-2">
                    <Provenance sourceUrl={signal.source_url} confidence={signal.confidence} />
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>
      )}

      {tab === 'Score' && (
        <Card title="Score breakdown" description="Every component, its weight and the reasoning behind it">
          {!c.score?.breakdown ? (
            <EmptyState title="Not scored yet" />
          ) : (
            <div className="space-y-4">
              {Object.entries(c.score.breakdown).map(([key, component]) => (
                <div key={key} className="border-b border-app pb-4 last:border-0 last:pb-0">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="font-medium">{titleCase(key)}</p>
                    <p className="text-sm tabular-nums">
                      <span className="font-semibold">{component.points.toFixed(1)}</span>
                      <span className="text-muted"> / {component.weight} points</span>
                    </p>
                  </div>
                  <div className="mt-2 h-1.5 overflow-hidden rounded-full surface-muted">
                    <div
                      className="h-full rounded-full bg-brand-500"
                      style={{ width: `${component.normalised * 100}%` }}
                    />
                  </div>
                  {component.reasons?.length > 0 && (
                    <ul className="mt-2 space-y-0.5 text-sm text-muted">
                      {component.reasons.map((reason, index) => (
                        <li key={index}>· {reason}</li>
                      ))}
                    </ul>
                  )}
                </div>
              ))}
              <div className="flex items-center justify-between border-t border-app pt-4">
                <p className="font-semibold">Total</p>
                <ScoreBadge score={c.score.total} category={c.score.category} />
              </div>
            </div>
          )}
        </Card>
      )}

      {tab === 'Evidence' && (
        <Card title="Findings and evidence" description="Each claim with the page that proves it">
          {!report?.findings.length ? (
            <EmptyState title="No findings recorded" />
          ) : (
            <ul className="space-y-4">
              {report.findings.map((finding) => (
                <li key={finding.id} className="border-b border-app pb-4 last:border-0 last:pb-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="badge surface-muted text-muted ring-transparent">
                      {titleCase(finding.category)}
                    </span>
                    <CertaintyBadge certainty={finding.certainty} />
                    {finding.impact && (
                      <span className="text-xs text-muted">impact: {finding.impact}</span>
                    )}
                  </div>
                  <p className="mt-1.5 text-sm">{finding.statement}</p>
                  {finding.evidence.map((item) => (
                    <div key={item.id} className="mt-2 rounded-lg surface-muted p-3">
                      {item.excerpt && (
                        <p className="text-xs italic text-muted">"{item.excerpt}"</p>
                      )}
                      {item.url && (
                        <a
                          className="mt-1 inline-flex items-center gap-1 break-all text-xs text-brand-600 hover:underline"
                          href={item.url}
                          target="_blank"
                          rel="noreferrer noopener"
                        >
                          {item.url}
                          <ExternalLink className="h-3 w-3 shrink-0" />
                        </a>
                      )}
                    </div>
                  ))}
                </li>
              ))}
            </ul>
          )}
        </Card>
      )}

      {tab === 'Activity' && (
        <Card title="Activity timeline" bodyClassName="p-0">
          {!activities.data?.length ? (
            <EmptyState title="No activity yet" message="Outreach and stage changes appear here." />
          ) : (
            <ol className="divide-y divide-[rgb(var(--border))]">
              {activities.data.map((activity) => (
                <li key={activity.id} className="flex gap-3 px-5 py-3.5">
                  <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-brand-500" />
                  <div className="min-w-0">
                    <p className="text-sm font-medium">{activity.title}</p>
                    {activity.body && <p className="mt-0.5 text-sm text-muted">{activity.body}</p>}
                    <p className="mt-0.5 text-xs text-muted">
                      {titleCase(activity.activity_type)} · {relativeTime(activity.created_at)}
                    </p>
                  </div>
                </li>
              ))}
            </ol>
          )}
        </Card>
      )}

      <Modal
        open={logOpen}
        onClose={() => setLogOpen(false)}
        title="Log outreach"
        footer={
          <>
            <button className="btn-secondary" onClick={() => setLogOpen(false)}>
              Cancel
            </button>
            <button
              className="btn-primary"
              disabled={logContact.isPending}
              onClick={() => logContact.mutate()}
            >
              {logContact.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
              Save
            </button>
          </>
        }
      >
        <p className="mb-4 text-sm text-muted">
          Recording this keeps the whole team from contacting {c.name} twice.
        </p>
        <div className="space-y-4">
          <div>
            <label className="label" htmlFor="status">
              Outcome
            </label>
            <select
              id="status"
              className="input"
              value={logStatus}
              onChange={(event) => setLogStatus(event.target.value as ContactStatusValue)}
            >
              {CONTACT_STATUSES.map((status) => (
                <option key={status} value={status}>
                  {titleCase(status)}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="label" htmlFor="note">
              Note
            </label>
            <textarea
              id="note"
              className="input min-h-[80px]"
              value={logNote}
              onChange={(event) => setLogNote(event.target.value)}
              placeholder="What happened on the call?"
            />
          </div>
        </div>
      </Modal>
    </>
  )
}
