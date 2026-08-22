import { useQuery } from '@tanstack/react-query'
import { FileText, ShieldCheck } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { errorMessage } from '../api/client'
import { listCompanies } from '../api/endpoints'
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
} from '../components/ui'

export default function Reports() {
  const [page, setPage] = useState(1)

  // Reports exist for qualified companies, so this is the same corpus filtered by score.
  const query = useQuery({
    queryKey: ['reports', page],
    queryFn: () =>
      listCompanies({
        page,
        page_size: 25,
        min_score: 60,
        sort_by: 'opportunity_score',
        sort_dir: 'desc',
      }),
  })

  return (
    <>
      <PageHeader
        title="AI reports"
        subtitle="Sales-intelligence briefs for qualified prospects. Each one must be approved by a human before any outreach."
      />

      <div className="card mb-6 flex items-start gap-3 p-4 text-sm">
        <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-brand-600" />
        <p className="text-muted">
          The platform never sends email or messages. Approving a report records your sign-off and
          moves the prospect to <strong>Ready to contact</strong> — the outreach itself stays with
          you.
        </p>
      </div>

      <Card bodyClassName="p-0">
        {query.isLoading ? (
          <SkeletonRows rows={8} cols={5} />
        ) : query.isError ? (
          <ErrorState message={errorMessage(query.error)} onRetry={() => void query.refetch()} />
        ) : !query.data?.items.length ? (
          <EmptyState
            title="No reports yet"
            message="Reports are written for companies that clear the quality gate and score 60 or above."
            icon={<FileText className="h-8 w-8" />}
            action={
              <Link className="btn-primary" to="/campaigns">
                Run a campaign
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
                  <th className="th">Score</th>
                  <th className="th">Completeness</th>
                  <th className="th">Researched</th>
                  <th className="th" />
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
                      <p className="text-xs text-muted">{company.domain}</p>
                    </td>
                    <td className="td text-sm">
                      {company.city ?? '—'}
                      {company.country_code ? `, ${company.country_code}` : ''}
                    </td>
                    <td className="td">
                      <ScoreBadge
                        score={company.opportunity_score}
                        category={company.opportunity_category}
                      />
                    </td>
                    <td className="td tabular-nums text-sm">
                      {Math.round(company.data_completeness * 100)}%
                    </td>
                    <td className="td text-sm text-muted">
                      {relativeTime(company.last_researched_at)}
                    </td>
                    <td className="td text-right">
                      <Link className="btn-secondary text-xs" to={`/companies/${company.id}`}>
                        Open report
                      </Link>
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
