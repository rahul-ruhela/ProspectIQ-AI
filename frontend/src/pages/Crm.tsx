import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CalendarClock, Kanban, Loader2 } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { errorMessage } from '../api/client'
import { changeStage, getPipeline, listFollowUps } from '../api/endpoints'
import type { PipelineCard as ProspectCardData, PipelineStage } from '../api/types'
import {
  Card,
  EmptyState,
  ErrorState,
  formatMoney,
  Loading,
  Modal,
  PageHeader,
  relativeTime,
  titleCase,
} from '../components/ui'
import { useAuth } from '../store/auth'

const STAGES: PipelineStage[] = [
  'discovered',
  'researching',
  'qualified',
  'ready_contact',
  'contacted',
  'reply_received',
  'meeting',
  'proposal',
  'negotiation',
  'customer',
  'lost',
]

function ProspectCard({
  card,
  onMove,
}: {
  card: ProspectCardData
  onMove: (card: ProspectCardData) => void
}) {
  return (
    <div className="card p-3">
      <Link
        to={`/companies/${card.company_id}`}
        className="block truncate text-sm font-medium hover:text-brand-600"
      >
        {card.company_name}
      </Link>
      <p className="truncate text-xs text-muted">
        {card.company_domain ?? 'No domain'}
        {card.country_code ? ` · ${card.country_code}` : ''}
      </p>
      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        {card.opportunity_score !== null && (
          <span className="badge surface-muted text-muted ring-transparent tabular-nums">
            {Math.round(card.opportunity_score)}
          </span>
        )}
        <span className="badge surface-muted text-muted ring-transparent">
          {titleCase(card.contact_status)}
        </span>
        {card.contact_attempts > 0 && (
          <span className="badge surface-muted text-muted ring-transparent">
            {card.contact_attempts} attempt{card.contact_attempts > 1 ? 's' : ''}
          </span>
        )}
      </div>
      {card.next_follow_up_at && (
        <p className="mt-2 flex items-center gap-1 text-xs text-amber-600 dark:text-amber-400">
          <CalendarClock className="h-3 w-3" />
          Follow up {relativeTime(card.next_follow_up_at)}
        </p>
      )}
      <button className="btn-ghost mt-2 w-full text-xs" onClick={() => onMove(card)}>
        Move stage
      </button>
    </div>
  )
}

export default function Crm() {
  const queryClient = useQueryClient()
  const { can } = useAuth()
  const [moving, setMoving] = useState<ProspectCardData | null>(null)
  const [targetStage, setTargetStage] = useState<PipelineStage>('contacted')
  const [note, setNote] = useState('')
  const [dealValue, setDealValue] = useState('')

  const board = useQuery({ queryKey: ['pipeline'], queryFn: () => getPipeline() })
  const followUps = useQuery({
    queryKey: ['follow-ups'],
    queryFn: () => listFollowUps({ days_ahead: 7 }),
  })

  const move = useMutation({
    mutationFn: () =>
      changeStage(moving!.company_id, {
        stage: targetStage,
        note: note || undefined,
        deal_value_usd: dealValue ? Number(dealValue) : undefined,
      }),
    onSuccess: () => {
      setMoving(null)
      setNote('')
      setDealValue('')
      void queryClient.invalidateQueries({ queryKey: ['pipeline'] })
    },
  })

  if (board.isLoading) return <Loading label="Loading your pipeline…" />
  if (board.isError) {
    return <ErrorState message={errorMessage(board.error)} onRetry={() => void board.refetch()} />
  }

  const data = board.data!
  const totalProspects = Object.values(data.counts).reduce((sum, n) => sum + n, 0)

  return (
    <>
      <PageHeader
        title="CRM"
        subtitle="Your pipeline. Contact status is tracked per prospect so nobody gets called twice."
        actions={
          <span className="text-sm text-muted">
            {totalProspects} prospects · {formatMoney(data.total_value_usd, 0)} open value
          </span>
        }
      />

      {followUps.data && followUps.data.length > 0 && (
        <Card
          className="mb-6 border-amber-300 dark:border-amber-500/30"
          title={`${followUps.data.length} follow-up${followUps.data.length > 1 ? 's' : ''} due in the next 7 days`}
          bodyClassName="p-0"
        >
          <ul className="divide-y divide-[rgb(var(--border))]">
            {followUps.data.slice(0, 5).map((card) => (
              <li key={card.id} className="flex items-center gap-3 px-5 py-2.5">
                <Link
                  to={`/companies/${card.company_id}`}
                  className="min-w-0 flex-1 truncate text-sm font-medium hover:text-brand-600"
                >
                  {card.company_name}
                </Link>
                <span className="text-xs text-muted">{titleCase(card.stage)}</span>
                <span className="text-xs text-amber-600 dark:text-amber-400">
                  {relativeTime(card.next_follow_up_at)}
                </span>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {totalProspects === 0 ? (
        <Card>
          <EmptyState
            title="Your pipeline is empty"
            message="Qualified prospects land in the pipeline automatically once a research job finds them."
            icon={<Kanban className="h-8 w-8" />}
            action={
              <Link className="btn-primary" to="/campaigns">
                Start a campaign
              </Link>
            }
          />
        </Card>
      ) : (
        <div className="overflow-x-auto pb-4">
          <div className="flex gap-4" style={{ minWidth: `${STAGES.length * 17}rem` }}>
            {STAGES.map((stage) => {
              const cards = data.stages[stage] ?? []
              return (
                <div key={stage} className="w-64 shrink-0">
                  <div className="mb-2 flex items-center justify-between px-1">
                    <p className="text-sm font-semibold">{titleCase(stage)}</p>
                    <span className="badge surface-muted text-muted ring-transparent tabular-nums">
                      {data.counts[stage] ?? 0}
                    </span>
                  </div>
                  <div className="min-h-[8rem] space-y-2 rounded-xl surface-muted p-2">
                    {cards.length === 0 ? (
                      <p className="px-2 py-6 text-center text-xs text-muted">Empty</p>
                    ) : (
                      cards.map((card) => (
                        <ProspectCard
                          key={card.id}
                          card={card}
                          onMove={(selected) => {
                            setMoving(selected)
                            setTargetStage(selected.stage)
                          }}
                        />
                      ))
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      <Modal
        open={Boolean(moving)}
        onClose={() => setMoving(null)}
        title={`Move ${moving?.company_name ?? ''}`}
        footer={
          <>
            <button className="btn-secondary" onClick={() => setMoving(null)}>
              Cancel
            </button>
            <button
              className="btn-primary"
              disabled={!can('sales_user') || move.isPending}
              onClick={() => move.mutate()}
            >
              {move.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
              Move
            </button>
          </>
        }
      >
        <div className="space-y-4">
          <div>
            <label className="label" htmlFor="stage">
              Stage
            </label>
            <select
              id="stage"
              className="input"
              value={targetStage}
              onChange={(event) => setTargetStage(event.target.value as PipelineStage)}
            >
              {STAGES.map((stage) => (
                <option key={stage} value={stage}>
                  {titleCase(stage)}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="label" htmlFor="deal">
              Deal value (USD, optional)
            </label>
            <input
              id="deal"
              className="input"
              type="number"
              min={0}
              value={dealValue}
              onChange={(event) => setDealValue(event.target.value)}
            />
          </div>
          <div>
            <label className="label" htmlFor="stage-note">
              Note
            </label>
            <textarea
              id="stage-note"
              className="input min-h-[70px]"
              value={note}
              onChange={(event) => setNote(event.target.value)}
            />
          </div>
        </div>
      </Modal>
    </>
  )
}
