/**
 * Live "department floor" view of the AI agents working a research job.
 *
 * A research job dispatches many agents against many companies, and a progress bar
 * flattens all of that into one number. This shows the roster as a grid of desks so
 * concurrent work reads at a glance: who is busy right now, who has finished, who has
 * not been called yet, and how many companies each has handled.
 *
 * Everything is derived from the AgentTask rows the page already polls — nothing here
 * invents activity. When the job is not running, the same grid renders statically as
 * a summary of what each agent did.
 */
import { useMemo } from 'react'
import type { AgentTask } from '../api/types'

/**
 * The pipeline order agents actually run in (see CEOOrchestratorAgent). Grouping by
 * phase is what makes concurrency legible: the per-company agents in the middle are
 * the ones that light up together.
 */
const PHASES: { label: string; agents: { key: string; name: string }[] }[] = [
  {
    label: 'Plan',
    agents: [
      { key: 'ceo_orchestrator', name: 'Orchestrator' },
      { key: 'global_search', name: 'Global Search' },
      { key: 'business_discovery', name: 'Discovery' },
    ],
  },
  {
    label: 'Inspect the website',
    agents: [
      { key: 'website_scraping', name: 'Scraper' },
      { key: 'technology_detection', name: 'Tech Detection' },
      { key: 'website_intelligence', name: 'Web Intelligence' },
      { key: 'company_verification', name: 'Verification' },
    ],
  },
  {
    label: 'Find the people',
    agents: [
      { key: 'decision_maker', name: 'Decision Makers' },
      { key: 'contact_enrichment', name: 'Contacts' },
      { key: 'email_verification', name: 'Email Check' },
      { key: 'phone_intelligence', name: 'Phone Check' },
    ],
  },
  {
    label: 'Judge the opportunity',
    agents: [
      { key: 'buying_signal', name: 'Buying Signals' },
      { key: 'ai_opportunity', name: 'AI Opportunity' },
      { key: 'lead_quality', name: 'Lead Quality' },
      { key: 'opportunity_scoring', name: 'Scoring' },
    ],
  },
]

type Activity = 'idle' | 'running' | 'done' | 'failed'

interface AgentActivity {
  status: Activity
  completed: number
  failed: number
}

function summarise(tasks: AgentTask[]): Map<string, AgentActivity> {
  const map = new Map<string, AgentActivity>()
  for (const task of tasks) {
    const current = map.get(task.agent_key) ?? { status: 'idle' as Activity, completed: 0, failed: 0 }
    const status = String(task.status).toLowerCase()
    if (status === 'running') current.status = 'running'
    if (status === 'completed') {
      current.completed += 1
      // A later completion must not overwrite a concurrently running task.
      if (current.status !== 'running') current.status = 'done'
    }
    if (status === 'failed') {
      current.failed += 1
      if (current.status === 'idle') current.status = 'failed'
    }
    map.set(task.agent_key, current)
  }
  return map
}

const DOT: Record<Activity, string> = {
  running: 'bg-sky-500',
  done: 'bg-emerald-500',
  failed: 'bg-rose-500',
  idle: 'bg-slate-300 dark:bg-slate-700',
}

export default function AgentFloor({ tasks, live }: { tasks: AgentTask[]; live: boolean }) {
  const activity = useMemo(() => summarise(tasks), [tasks])
  const runningCount = useMemo(
    () => [...activity.values()].filter((a) => a.status === 'running').length,
    [activity],
  )

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-slate-500 dark:text-slate-400">
        {live ? (
          <span className="inline-flex items-center gap-2 font-medium text-sky-600 dark:text-sky-400">
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-sky-400 opacity-75" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-sky-500" />
            </span>
            {runningCount > 0
              ? `${runningCount} agent${runningCount === 1 ? '' : 's'} working right now`
              : 'Department active'}
          </span>
        ) : (
          <span className="font-medium">Department idle</span>
        )}
        <Legend />
      </div>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {PHASES.map((phase) => (
          <section
            key={phase.label}
            className="rounded-xl border border-slate-200 bg-slate-50/60 p-3 dark:border-slate-800 dark:bg-slate-900/40"
          >
            <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
              {phase.label}
            </h3>
            <ul className="space-y-1.5">
              {phase.agents.map((agent) => {
                const state = activity.get(agent.key) ?? {
                  status: 'idle' as Activity,
                  completed: 0,
                  failed: 0,
                }
                const working = state.status === 'running'
                return (
                  <li
                    key={agent.key}
                    className={[
                      'flex items-center gap-2 rounded-lg border px-2.5 py-2 text-sm transition-colors',
                      working
                        ? 'border-sky-300 bg-sky-50 dark:border-sky-800 dark:bg-sky-950/40'
                        : 'border-transparent bg-white dark:bg-slate-900',
                    ].join(' ')}
                  >
                    <span className="relative flex h-2 w-2 shrink-0">
                      {working ? (
                        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-sky-400 opacity-75" />
                      ) : null}
                      <span
                        className={`relative inline-flex h-2 w-2 rounded-full ${DOT[state.status]}`}
                      />
                    </span>
                    <span
                      className={
                        working
                          ? 'font-medium text-sky-700 dark:text-sky-300'
                          : 'text-slate-700 dark:text-slate-300'
                      }
                    >
                      {agent.name}
                    </span>
                    <span className="ml-auto shrink-0 text-xs tabular-nums text-slate-400 dark:text-slate-500">
                      {state.failed > 0 ? (
                        <span className="text-rose-500">{state.failed}✕ </span>
                      ) : null}
                      {state.completed > 0 ? state.completed : null}
                    </span>
                  </li>
                )
              })}
            </ul>
          </section>
        ))}
      </div>
    </div>
  )
}

function Legend() {
  const items: [Activity, string][] = [
    ['running', 'working'],
    ['done', 'completed'],
    ['failed', 'failed'],
    ['idle', 'not started'],
  ]
  return (
    <span className="flex flex-wrap items-center gap-3">
      {items.map(([state, label]) => (
        <span key={state} className="inline-flex items-center gap-1.5">
          <span className={`h-2 w-2 rounded-full ${DOT[state]}`} />
          {label}
        </span>
      ))}
    </span>
  )
}
