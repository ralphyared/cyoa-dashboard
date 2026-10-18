import { cx as clsx } from './ui'
import { ChevronsUpDown, Plus, TriangleAlert } from 'lucide-react'
import { useMemo, useRef, useState, type KeyboardEvent } from 'react'
import { useScenes } from '@/lib/queries'
import type { Scene } from '@/lib/types'
import { Popover, PopoverContent, PopoverTrigger } from './ui'

export function sceneLabel(scene: Pick<Scene, 'id' | 'title'>): string {
  return scene.title || scene.id
}

export function matchScene(scene: Scene, query: string): boolean {
  const q = query.trim().toLowerCase()
  if (!q) return true
  return scene.title.toLowerCase().includes(q) || scene.id.includes(q)
}

export function ScenePicker({
  gameId,
  value,
  onChange,
  onCreate,
  placeholder = 'Choose a scene…',
  className,
  allowNone,
  size = 'md',
}: {
  gameId: string
  value: string
  onChange: (sceneId: string) => void
  onCreate?: (title: string) => Promise<string>
  placeholder?: string
  className?: string
  allowNone?: string
  size?: 'sm' | 'md'
}) {
  const scenes = useScenes(gameId)
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [active, setActive] = useState(0)
  const [creating, setCreating] = useState(false)
  const listRef = useRef<HTMLDivElement>(null)
  const current = scenes.find((s) => s.id === value)

  const filtered = useMemo(
    () => scenes.filter((s) => matchScene(s, query)).slice(0, 200),
    [scenes, query],
  )
  type Option = { kind: 'scene'; scene: Scene } | { kind: 'none' } | { kind: 'create' }
  const options: Option[] = [
    ...(allowNone && !query ? [{ kind: 'none' as const }] : []),
    ...filtered.map((scene) => ({ kind: 'scene' as const, scene })),
    ...(onCreate && query.trim() ? [{ kind: 'create' as const }] : []),
  ]

  async function pick(option: Option) {
    if (option.kind === 'scene') onChange(option.scene.id)
    else if (option.kind === 'none') onChange('')
    else if (onCreate) {
      setCreating(true)
      try {
        onChange(await onCreate(query.trim()))
      } finally {
        setCreating(false)
      }
    }
    setOpen(false)
    setQuery('')
  }

  function onKeyDown(e: KeyboardEvent) {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActive((a) => Math.min(a + 1, options.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActive((a) => Math.max(a - 1, 0))
    } else if (e.key === 'Enter') {
      e.preventDefault()
      const option = options[active]
      if (option) void pick(option)
    }
  }

  const missing = value && !current
  return (
    <Popover
      open={open}
      onOpenChange={(o) => {
        setOpen(o)
        if (!o) setQuery('')
        setActive(0)
      }}
    >
      <PopoverTrigger asChild>
        <button
          type="button"
          className={clsx(
            'flex min-w-0 items-center gap-2 rounded-md border bg-surface-900 px-2.5 text-left text-sm',
            'hover:border-zinc-500 focus:border-accent-600 focus:outline-none',
            size === 'sm' ? 'h-7' : 'h-8',
            missing ? 'border-red-500/60 text-red-300' : 'border-surface-700',
            className,
          )}
        >
          {missing && <TriangleAlert className="size-3.5 shrink-0" />}
          <span className={clsx('min-w-0 flex-1 truncate', !value && 'text-zinc-500')}>
            {current ? sceneLabel(current) : value ? `${value} (missing)` : allowNone ?? placeholder}
          </span>
          {current && current.title && (
            <span className="shrink-0 font-mono text-[11px] text-zinc-500">{current.id}</span>
          )}
          <ChevronsUpDown className="size-3.5 shrink-0 text-zinc-500" />
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-80 p-0">
        <input
          autoFocus
          value={query}
          onChange={(e) => {
            setQuery(e.target.value)
            setActive(0)
          }}
          onKeyDown={onKeyDown}
          placeholder={onCreate ? 'Search, or type a new scene title…' : 'Search scenes…'}
          className="w-full border-b border-surface-600 bg-transparent px-3 py-2 text-sm text-zinc-100 outline-none placeholder:text-zinc-500"
        />
        <div ref={listRef} className="max-h-72 overflow-y-auto p-1">
          {options.length === 0 && <div className="px-2 py-3 text-sm text-zinc-500">No scenes match.</div>}
          {options.map((option, i) => (
            <button
              key={option.kind === 'scene' ? option.scene.pk : option.kind}
              type="button"
              onMouseEnter={() => setActive(i)}
              onClick={() => void pick(option)}
              className={clsx(
                'flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-sm',
                i === active ? 'bg-surface-700' : '',
              )}
            >
              {option.kind === 'scene' && (
                <>
                  <span className="min-w-0 flex-1 truncate text-zinc-200">{sceneLabel(option.scene)}</span>
                  <span className="shrink-0 font-mono text-[11px] text-zinc-500">{option.scene.id}</span>
                </>
              )}
              {option.kind === 'none' && <span className="text-zinc-400 italic">{allowNone}</span>}
              {option.kind === 'create' && (
                <span className="flex items-center gap-1.5 text-accent-300">
                  <Plus className="size-3.5" />
                  {creating ? 'Creating…' : <>Create new scene “{query.trim()}”</>}
                </span>
              )}
            </button>
          ))}
        </div>
      </PopoverContent>
    </Popover>
  )
}
