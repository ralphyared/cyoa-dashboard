import * as DialogPrimitive from '@radix-ui/react-dialog'
import { FileText, Settings } from 'lucide-react'
import { useMemo, useState, type KeyboardEvent } from 'react'
import { useNavigate } from 'react-router'
import { matchScene, sceneLabel } from '@/components/ScenePicker'
import { cx } from '@/components/ui'
import { useScenes } from '@/lib/queries'
import { useWorkspace } from './context'

const PAGES = [
  { label: 'Graph', path: 'graph' },
  { label: 'Variables', path: 'variables' },
  { label: 'Items', path: 'items' },
  { label: 'Rules', path: 'rules' },
  { label: 'Chapters', path: 'chapters' },
  { label: 'Settings', path: 'settings' },
  { label: 'Help & reference', path: 'reference' },
]

export function CommandPalette({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const { gameId } = useWorkspace()
  const scenes = useScenes(gameId)
  const navigate = useNavigate()
  const [query, setQuery] = useState('')
  const [active, setActive] = useState(0)

  const results = useMemo(() => {
    const q = query.trim().toLowerCase()
    const pages = PAGES.filter((p) => !q || p.label.toLowerCase().includes(q)).map((p) => ({
      key: `page:${p.path}`,
      label: p.label,
      detail: 'page',
      path: `/games/${gameId}/${p.path}`,
      page: true,
    }))
    const sceneResults = scenes
      .filter((s) => matchScene(s, q))
      .slice(0, 50)
      .map((s) => ({
        key: `scene:${s.pk}`,
        label: sceneLabel(s),
        detail: s.id,
        path: `/games/${gameId}/scenes/${s.pk}`,
        page: false,
      }))
    return q ? [...sceneResults, ...pages] : [...pages, ...sceneResults]
  }, [query, scenes, gameId])

  function go(index: number) {
    const result = results[index]
    if (!result) return
    navigate(result.path)
    onOpenChange(false)
    setQuery('')
  }

  function onKeyDown(e: KeyboardEvent) {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActive((a) => Math.min(a + 1, results.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActive((a) => Math.max(a - 1, 0))
    } else if (e.key === 'Enter') {
      e.preventDefault()
      go(active)
    }
  }

  return (
    <DialogPrimitive.Root
      open={open}
      onOpenChange={(o) => {
        onOpenChange(o)
        setQuery('')
        setActive(0)
      }}
    >
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-black/50" />
        <DialogPrimitive.Content className="fixed top-[15vh] left-1/2 z-50 w-[min(36rem,calc(100vw-2rem))] -translate-x-1/2 overflow-hidden rounded-lg border border-surface-600 bg-surface-850 shadow-2xl">
          <DialogPrimitive.Title className="sr-only">Jump to</DialogPrimitive.Title>
          <DialogPrimitive.Description className="sr-only">Search scenes and pages</DialogPrimitive.Description>
          <input
            autoFocus
            value={query}
            onChange={(e) => {
              setQuery(e.target.value)
              setActive(0)
            }}
            onKeyDown={onKeyDown}
            placeholder="Jump to a scene or page…"
            className="w-full border-b border-surface-600 bg-transparent px-4 py-3 text-sm text-zinc-100 outline-none placeholder:text-zinc-500"
          />
          <div className="max-h-80 overflow-y-auto p-1.5">
            {results.length === 0 && <div className="px-3 py-4 text-sm text-zinc-500">Nothing found.</div>}
            {results.map((r, i) => (
              <button
                key={r.key}
                type="button"
                onMouseEnter={() => setActive(i)}
                onClick={() => go(i)}
                className={cx(
                  'flex w-full items-center gap-2.5 rounded px-3 py-2 text-left text-sm',
                  i === active ? 'bg-surface-700' : '',
                )}
              >
                {r.page ? <Settings className="size-3.5 text-zinc-500" /> : <FileText className="size-3.5 text-zinc-500" />}
                <span className="min-w-0 flex-1 truncate text-zinc-200">{r.label}</span>
                <span className="font-mono text-xs text-zinc-500">{r.detail}</span>
              </button>
            ))}
          </div>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  )
}
