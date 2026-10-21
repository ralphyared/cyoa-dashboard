import { AlertTriangle, ChevronRight, CircleAlert, Eye, EyeOff, PartyPopper, X } from 'lucide-react'
import { useMemo, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router'
import { Button, Empty, Segmented, Spinner, cx, useReadOnly } from '@/components/ui'
import { plural } from '@/lib/format'
import { useGameActions, useIssues, useScenes } from '@/lib/queries'
import type { Issue, Scene } from '@/lib/types'
import { useWorkspace } from './context'
import { issueLink } from './Workspace'

const FIELD_NAMES: Record<string, string> = {
  text: 'text',
  choice_text: 'choice text',
  condition: 'condition',
  effects: 'effects',
  on_enter: 'arrival effects',
  target: 'destination',
  chapter: 'chapter',
  goto: 'go to',
  status_format: 'status bar',
  intro: 'intro text',
  start_scene: 'start scene',
  initial: 'starting value',
  min: 'minimum',
  max: 'maximum',
}

export function issueTitle(issue: Issue): string {
  const parts: string[] = []
  if (issue.scene) parts.push(`Scene “${issue.scene}”`)
  if (issue.choice) parts.push('choice')
  if (issue.rule) parts.push(`Rule ${issue.rule}`)
  if (issue.variable) parts.push(`Variable “${issue.variable}”`)
  if (issue.item) parts.push(`Item “${issue.item}”`)
  if (issue.chapter) parts.push(`Chapter “${issue.chapter}”`)
  if (issue.field) parts.push(FIELD_NAMES[issue.field] ?? issue.field)
  if (parts.length === 0) return 'Game'
  return parts.join(' · ')
}

export function IssuesPanel({ onClose }: { onClose: () => void }) {
  const { gameId } = useWorkspace()
  const issues = useIssues(gameId)
  const scenes = useScenes(gameId)
  const actions = useGameActions(gameId)
  const [filter, setFilter] = useState<'all' | 'error' | 'warning'>('all')
  const [showHidden, setShowHidden] = useState(false)
  const readOnly = useReadOnly()
  const list = useMemo(
    () => (issues.data?.issues ?? []).filter((i) => filter === 'all' || i.severity === filter),
    [issues.data, filter],
  )
  const stats = issues.data?.stats
  const hidden = filter === 'error' ? [] : (issues.data?.hidden ?? [])

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex items-center gap-2 border-b border-surface-700 px-3 py-2">
        <div className="text-sm font-semibold text-zinc-200">Problems</div>
        <Segmented
          size="xs"
          value={filter}
          onChange={setFilter}
          options={[
            { value: 'all', label: 'All' },
            { value: 'error', label: 'Errors' },
            { value: 'warning', label: 'Warnings' },
          ]}
        />
        <Button className="ml-auto" size="sm" variant="ghost" icon={<X className="size-4" />} onClick={onClose} aria-label="Close" />
      </div>
      {stats && (
        <div className="flex gap-4 border-b border-surface-700 px-3 py-2 text-xs text-zinc-500">
          <span>{plural(stats.scenes, 'scene')}</span>
          <span>{plural(stats.words, 'word')}</span>
          <span>{plural(stats.choices, 'choice')}</span>
          <span>{plural(stats.endings, 'ending')}</span>
        </div>
      )}
      <div className="min-h-0 flex-1 overflow-y-auto p-2">
        {issues.isLoading && <Spinner />}
        {issues.data && list.length === 0 && (
          <Empty icon={<PartyPopper className="size-8" />} title="Nothing to fix">
            {filter === 'all' ? 'No errors or warnings.' : `No ${filter}s.`}
          </Empty>
        )}
        <ul className="flex flex-col gap-0.5">
          {list.map((issue, i) => (
            <IssueRow key={i} issue={issue} gameId={gameId} scenes={scenes}>
              {issue.key && !readOnly && (
                <Button
                  size="xs"
                  variant="ghost"
                  className="mt-1 shrink-0 text-zinc-400"
                  icon={<EyeOff className="size-3.5" />}
                  title="I've checked this: hide the warning (it comes back if this changes)"
                  onClick={() => actions.setWarningHidden(issue, true)}
                >
                  Hide
                </Button>
              )}
            </IssueRow>
          ))}
        </ul>
        {hidden.length > 0 && (
          <div className="mt-3 border-t border-surface-700 pt-2">
            <button
              type="button"
              className="flex items-center gap-1.5 px-2 py-1 text-xs text-zinc-500 hover:text-zinc-300"
              aria-expanded={showHidden}
              onClick={() => setShowHidden(!showHidden)}
            >
              <ChevronRight className={cx('size-3.5 transition-transform', showHidden && 'rotate-90')} />
              <EyeOff className="size-3.5" /> Hidden ({hidden.length})
            </button>
            {showHidden && (
              <ul className="flex flex-col gap-0.5 opacity-75">
                {hidden.map((issue, i) => (
                  <IssueRow key={i} issue={issue} gameId={gameId} scenes={scenes}>
                    {!readOnly && (
                      <Button
                        size="xs"
                        variant="ghost"
                        className="mt-1 shrink-0 text-zinc-400"
                        icon={<Eye className="size-3.5" />}
                        onClick={() => actions.setWarningHidden(issue, false)}
                      >
                        Show again
                      </Button>
                    )}
                  </IssueRow>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

function IssueRow({
  issue,
  gameId,
  scenes,
  children,
}: {
  issue: Issue
  gameId: string
  scenes: Scene[]
  children?: ReactNode
}) {
  const navigate = useNavigate()
  const link = issueLink(issue, gameId, scenes)
  return (
    <li className="flex items-start gap-1">
      <button
        type="button"
        disabled={!link}
        onClick={() => {
          if (!link) return
          const params = new URLSearchParams()
          if (issue.choice) params.set('choice', issue.choice)
          if (issue.field) params.set('field', issue.field)
          navigate(params.size ? `${link}?${params}` : link)
        }}
        className="flex min-w-0 flex-1 gap-2 rounded px-2 py-1.5 text-left hover:bg-surface-800 disabled:cursor-default disabled:hover:bg-transparent"
      >
        {issue.severity === 'error' ? (
          <CircleAlert className="mt-0.5 size-3.5 shrink-0 text-red-400" />
        ) : (
          <AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-amber-400" />
        )}
        <div className="min-w-0">
          <div className={cx('text-sm', issue.severity === 'error' ? 'text-zinc-100' : 'text-zinc-300')}>
            {issue.message}
          </div>
          <div className="text-xs text-zinc-500">{issueTitle(issue)}</div>
        </div>
      </button>
      {children}
    </li>
  )
}
