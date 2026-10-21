import { ArrowDown, ArrowUp, Layers, Plus, Trash2 } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Button, Empty, Input, Popover, PopoverContent, PopoverTrigger, cx, useReadOnly } from '@/components/ui'
import { slugify, slugError } from '@/lib/format'
import { useGameActions, useMeta, useScenes } from '@/lib/queries'
import type { Chapter } from '@/lib/types'
import { useWorkspace } from './context'
import { ConfirmDelete, PageShell, RenameButton } from './shared'

const SWATCHES = [
  '#f87171', '#fb923c', '#fbbf24', '#a3e635', '#34d399', '#22d3ee',
  '#60a5fa', '#a78bfa', '#f472b6', '#94a3b8',
]

export function ChaptersPage() {
  const { gameId } = useWorkspace()
  const meta = useMeta(gameId)
  const scenes = useScenes(gameId)
  const actions = useGameActions(gameId)
  const [title, setTitle] = useState('')
  const [deleting, setDeleting] = useState<Chapter | null>(null)
  const readOnly = useReadOnly()
  if (!meta) return null
  const chapters = meta.chapters
  const ids = chapters.map((c) => c.id)
  const newId = slugify(title, '')
  const idError = title ? slugError(newId, ids) : null

  const save = (next: Chapter[]) => actions.updateMeta({ chapters: next })
  const change = (index: number, changes: Partial<Chapter>) =>
    save(chapters.map((c, i) => (i === index ? { ...c, ...changes } : c)))
  const move = (index: number, delta: number) => {
    const next = [...chapters]
    const [c] = next.splice(index, 1)
    next.splice(index + delta, 0, c)
    save(next)
  }

  function add(e: FormEvent) {
    e.preventDefault()
    if (!newId || idError) return
    save([...chapters, { id: newId, title: title.trim(), color: SWATCHES[chapters.length % SWATCHES.length] }])
    setTitle('')
  }

  function remove(chapter: Chapter) {
    for (const scene of scenes) {
      if (scene.chapter === chapter.id) actions.updateScene(scene.pk, { chapter: null })
    }
    save(chapters.filter((c) => c.id !== chapter.id))
  }

  return (
    <PageShell
      title="Chapters"
      description="Group scenes into chapters. Players see the chapter title in the top-right corner of each scene; the dashboard uses chapters to organize the sidebar and color the graph."
    >
      {chapters.length === 0 ? (
        <Empty icon={<Layers className="size-10" />} title="No chapters yet" />
      ) : (
        <div className="flex flex-col gap-2">
          {chapters.map((chapter, i) => {
            const count = scenes.filter((s) => s.chapter === chapter.id).length
            return (
              <div key={chapter.id} className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-lg border border-surface-700 bg-surface-900 px-3 py-2">
                <Popover>
                  <PopoverTrigger asChild>
                    <button
                      type="button"
                      disabled={readOnly}
                      className="size-6 shrink-0 rounded-full border border-surface-600 disabled:cursor-default"
                      style={{ background: chapter.color || '#3f3f46' }}
                      aria-label="Chapter color"
                    />
                  </PopoverTrigger>
                  <PopoverContent className="grid grid-cols-5 gap-1.5 p-2">
                    {SWATCHES.map((color) => (
                      <button
                        key={color}
                        type="button"
                        onClick={() => change(i, { color })}
                        className={cx('size-6 rounded-full', chapter.color === color && 'ring-2 ring-white')}
                        style={{ background: color }}
                        aria-label={color}
                      />
                    ))}
                  </PopoverContent>
                </Popover>
                <Input className="min-w-40 flex-1" value={chapter.title} placeholder="Chapter title" onChange={(e) => change(i, { title: e.target.value })} />
                <RenameButton kind="chapter" current={chapter.id} taken={ids} />
                <span className="text-xs text-zinc-500 sm:w-20 sm:text-right">
                  {count} scene{count === 1 ? '' : 's'}
                </span>
                {!readOnly && (
                  <>
                    <Button size="sm" variant="ghost" icon={<ArrowUp className="size-3.5" />} disabled={i === 0} onClick={() => move(i, -1)} aria-label="Move up" />
                    <Button size="sm" variant="ghost" icon={<ArrowDown className="size-3.5" />} disabled={i === chapters.length - 1} onClick={() => move(i, 1)} aria-label="Move down" />
                    <Button size="sm" variant="ghost" icon={<Trash2 className="size-3.5" />} onClick={() => setDeleting(chapter)} aria-label="Delete chapter" />
                  </>
                )}
              </div>
            )
          })}
        </div>
      )}
      <form onSubmit={add} className={cx('flex flex-wrap items-start gap-2', readOnly && 'hidden')}>
        <Input className="w-full sm:w-72" placeholder="New chapter title, e.g. Chapter 1: The Road" value={title} onChange={(e) => setTitle(e.target.value)} />
        <Button type="submit" icon={<Plus className="size-4" />} disabled={!newId || !!idError}>
          Add chapter
        </Button>
        {idError && <span className="py-2 text-xs text-red-400">{idError}</span>}
      </form>
      <ConfirmDelete
        open={deleting !== null}
        onOpenChange={(o) => !o && setDeleting(null)}
        title={`Delete chapter “${deleting?.title || deleting?.id}”?`}
        description="Its scenes are kept; they just won't belong to a chapter anymore."
        onConfirm={() => deleting && remove(deleting)}
      />
    </PageShell>
  )
}
