import { useQuery } from '@tanstack/react-query'
import { diffWords } from 'diff'
import { RotateCcw } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Badge, Button, Dialog, Empty, Spinner, cx, useReadOnly } from '@/components/ui'
import { api } from '@/lib/api'
import { dateTime } from '@/lib/format'
import { useGameActions } from '@/lib/queries'
import type { Revision, Scene } from '@/lib/types'
import { useWorkspace } from './context'

const REASONS: Record<string, string> = {
  edit: 'edited',
  created: 'created',
  rename: 'renamed',
  restored: 'restored',
  deleted: 'deleted',
}

function fieldChanges(old: Revision['snapshot'], current: Scene): string[] {
  const changes: string[] = []
  if (old.title !== current.title) changes.push(`Title was “${old.title || '(none)'}”`)
  if (old.id !== current.id) changes.push(`Id was ${old.id}`)
  if (old.chapter !== current.chapter) changes.push(`Chapter was ${old.chapter ?? 'none'}`)
  if (JSON.stringify(old.ending) !== JSON.stringify(current.ending)) {
    changes.push(old.ending ? `Was an ending (${old.ending.kind})` : 'Was not an ending')
  }
  if (old.on_enter !== current.on_enter) changes.push('Arrival effects differ')
  if (old.art !== current.art) changes.push('ASCII art differs')
  if (JSON.stringify(old.choices) !== JSON.stringify(current.choices)) {
    const texts = old.choices.map((c) => c.text || '(untitled)').join(', ')
    changes.push(`Choices were: ${texts || 'none'}`)
  }
  if (old.notes !== current.notes) changes.push('Notes differ')
  return changes
}

export function HistoryDialog({
  open,
  onOpenChange,
  scene,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  scene: Scene
}) {
  const { gameId } = useWorkspace()
  const actions = useGameActions(gameId)
  const revisions = useQuery({
    queryKey: ['revisions', gameId, scene.pk],
    queryFn: () => api.revisions(gameId, scene.pk),
    enabled: open,
    staleTime: 0,
  })
  const [selected, setSelected] = useState<number | null>(null)
  const [busy, setBusy] = useState(false)
  const readOnly = useReadOnly()
  useEffect(() => {
    if (open) void revisions.refetch()
    // refresh whenever the dialog opens
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])
  const list = revisions.data ?? []
  const revision = list.find((r) => r.id === selected) ?? list[1] ?? list[0]

  const diff = useMemo(
    () => (revision ? diffWords(revision.snapshot.text, scene.text) : []),
    [revision, scene.text],
  )
  const changes = revision ? fieldChanges(revision.snapshot, scene) : []
  const identical = diff.every((part) => !part.added && !part.removed) && changes.length === 0

  async function restore() {
    if (!revision) return
    setBusy(true)
    try {
      await actions.restoreRevision(scene.pk, revision.id)
      onOpenChange(false)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      wide
      title={`History of “${scene.title || scene.id}”`}
      description="Edits made within a few minutes of each other are grouped together."
      footer={
        <>
          <Button onClick={() => onOpenChange(false)}>Close</Button>
          {!readOnly && (
            <Button variant="primary" icon={<RotateCcw className="size-3.5" />} loading={busy} disabled={!revision || identical} onClick={() => void restore()}>
              Restore this version
            </Button>
          )}
        </>
      }
    >
      {revisions.isLoading ? (
        <Spinner />
      ) : list.length === 0 ? (
        <Empty title="No history yet" />
      ) : (
        <div className="flex min-h-80 gap-4">
          <ul className="flex w-56 shrink-0 flex-col gap-0.5 overflow-y-auto">
            {list.map((r, i) => (
              <li key={r.id}>
                <button
                  type="button"
                  onClick={() => setSelected(r.id)}
                  className={cx(
                    'flex w-full flex-col rounded px-2 py-1.5 text-left',
                    revision?.id === r.id ? 'bg-surface-700' : 'hover:bg-surface-800',
                  )}
                >
                  <span className="flex items-center gap-1.5 text-sm text-zinc-200">
                    {dateTime(r.updated_at)}
                    {i === 0 && <Badge tone="accent">current</Badge>}
                  </span>
                  <span className="text-xs text-zinc-500">
                    {REASONS[r.reason] ?? r.reason}
                    {r.by && <> by {r.by}</>}
                  </span>
                </button>
              </li>
            ))}
          </ul>
          <div className="min-w-0 flex-1">
            {revision && (
              <>
                <div className="mb-2 text-xs text-zinc-500">
                  Changes from this version to now:{' '}
                  <span className="text-red-300 line-through">removed since</span>{' '}
                  <span className="text-emerald-300">added since</span>
                </div>
                {changes.length > 0 && (
                  <ul className="mb-3 list-disc pl-5 text-sm text-zinc-300">
                    {changes.map((c) => (
                      <li key={c}>{c}</li>
                    ))}
                  </ul>
                )}
                <div className="rounded-md border border-surface-700 bg-surface-900 p-3 text-sm leading-relaxed whitespace-pre-wrap text-zinc-300">
                  {identical && <span className="text-zinc-500 italic">Same as the current version.</span>}
                  {!identical &&
                    diff.map((part, i) => (
                      <span
                        key={i}
                        className={cx(
                          part.added && 'bg-emerald-500/15 text-emerald-200',
                          part.removed && 'bg-red-500/15 text-red-300 line-through',
                        )}
                      >
                        {part.value}
                      </span>
                    ))}
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </Dialog>
  )
}
