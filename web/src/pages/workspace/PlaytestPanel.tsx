import { FitAddon } from '@xterm/addon-fit'
import { Terminal } from '@xterm/xterm'
import '@xterm/xterm/css/xterm.css'
import {
  ChevronDown,
  ChevronUp,
  Home,
  Minus,
  Play,
  Plus,
  RefreshCw,
  Square,
  TriangleAlert,
  X,
} from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router'
import { Button, Checkbox, Input, Select, Tip, cx } from '@/components/ui'
import { useMeta, useScenes } from '@/lib/queries'
import type { PlaytestState, Value } from '@/lib/types'
import { useWorkspace } from './context'

type ServerMessage =
  | { type: 'output'; data: string }
  | { type: 'state'; state: PlaytestState; scene_title: string; problems: string[] }
  | { type: 'exit'; code: number }
  | { type: 'error'; message: string }

type Status = 'connecting' | 'idle' | 'running' | 'exited' | 'disconnected'

export function PlaytestPanel({ onClose, visible }: { onClose: () => void; visible: boolean }) {
  const { gameId, playtestRequest } = useWorkspace()
  const meta = useMeta(gameId)
  const scenes = useScenes(gameId)
  const navigate = useNavigate()
  const host = useRef<HTMLDivElement>(null)
  const term = useRef<Terminal | null>(null)
  const fit = useRef<FitAddon | null>(null)
  const ws = useRef<WebSocket | null>(null)
  const queued = useRef<Record<string, unknown>[]>([])
  const [status, setStatus] = useState<Status>('connecting')
  const [state, setState] = useState<PlaytestState | null>(null)
  const [problems, setProblems] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)
  const [follow, setFollow] = useState(() => localStorage.getItem('cyoa.follow') === '1')
  const [showState, setShowState] = useState(true)
  const lastScene = useRef<string | null>(null)
  const [generation, setGeneration] = useState(0)

  const send = useCallback((message: Record<string, unknown>) => {
    const socket = ws.current
    if (socket && socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify(message))
    else queued.current.push(message)
  }, [])

  const size = () => ({ cols: term.current?.cols ?? 80, rows: term.current?.rows ?? 24 })

  const start = useCallback(
    (scene?: string, extra: Record<string, unknown> = {}) => {
      setError(null)
      setProblems([])
      term.current?.reset()
      setStatus('running')
      send({ type: 'start', ...size(), ...(scene ? { scene } : {}), ...extra })
      term.current?.focus()
    },
    [send],
  )

  // terminal
  useEffect(() => {
    if (!host.current) return
    const t = new Terminal({
      fontFamily: 'ui-monospace, "JetBrains Mono", "Cascadia Code", Menlo, Consolas, monospace',
      fontSize: 13,
      cursorBlink: true,
      convertEol: false,
      theme: {
        background: '#0b0b0e',
        foreground: '#e4e4e7',
        cursor: '#22d3ee',
        selectionBackground: '#155e7566',
      },
    })
    const f = new FitAddon()
    t.loadAddon(f)
    t.open(host.current)
    term.current = t
    fit.current = f
    const disposable = t.onData((data) => send({ type: 'input', data }))
    const observer = new ResizeObserver(() => {
      if (!host.current || host.current.offsetWidth === 0) return
      try {
        f.fit()
        send({ type: 'resize', cols: t.cols, rows: t.rows })
      } catch {
        // not visible yet
      }
    })
    observer.observe(host.current)
    return () => {
      observer.disconnect()
      disposable.dispose()
      t.dispose()
      term.current = null
    }
  }, [send])

  // connection
  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const socket = new WebSocket(`${protocol}//${window.location.host}/api/games/${gameId}/playtest`)
    ws.current = socket
    setStatus('connecting')
    socket.onopen = () => {
      setStatus('idle')
      for (const message of queued.current.splice(0)) socket.send(JSON.stringify(message))
    }
    socket.onmessage = (event) => {
      const message = JSON.parse(event.data) as ServerMessage
      if (message.type === 'output') term.current?.write(message.data)
      else if (message.type === 'state') {
        setState(message.state)
        setProblems(message.problems)
        setStatus('running')
      } else if (message.type === 'exit') setStatus('exited')
      else if (message.type === 'error') setError(message.message)
    }
    socket.onclose = (event) => {
      if (ws.current !== socket) return
      setStatus('disconnected')
      if (event.code === 4401) setError('Your session expired; log in again.')
    }
    return () => {
      ws.current = null
      socket.close()
    }
  }, [gameId, generation])

  // start requests from the rest of the dashboard ("Play from here", "Playtest")
  useEffect(() => {
    if (playtestRequest) start(playtestRequest.scene)
  }, [playtestRequest, start])

  useEffect(() => {
    if (visible) {
      requestAnimationFrame(() => {
        try {
          fit.current?.fit()
        } catch {
          // ignore
        }
        term.current?.focus()
      })
    }
  }, [visible])

  // follow along in the editor
  useEffect(() => {
    if (!state) return
    if (follow && state.scene !== lastScene.current) {
      const scene = scenes.find((s) => s.id === state.scene)
      if (scene) navigate(`/games/${gameId}/scenes/${scene.pk}`)
    }
    lastScene.current = state.scene
    // only react to the playtest moving, not to scene list edits
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state?.scene, follow])

  const currentScene = state ? scenes.find((s) => s.id === state.scene) : undefined

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex items-center gap-1 border-b border-surface-700 px-2 py-1.5">
        <div className="mr-1 text-sm font-semibold text-zinc-200">Playtest</div>
        <Tip content="New game from the start scene">
          <Button size="sm" variant="ghost" icon={<Play className="size-3.5" />} onClick={() => start(meta?.start_scene)}>
            Start
          </Button>
        </Tip>
        <Tip content="Open the title screen, like a player would">
          <Button size="sm" variant="ghost" icon={<Home className="size-3.5" />} onClick={() => start()} />
        </Tip>
        <Tip content="Reload with your latest edits, keeping your place and stats">
          <Button
            size="sm"
            variant="ghost"
            icon={<RefreshCw className="size-3.5" />}
            disabled={!state}
            onClick={() => {
              term.current?.reset()
              send({ type: 'reload' })
              term.current?.focus()
            }}
          >
            Reload
          </Button>
        </Tip>
        <Tip content="Stop">
          <Button
            size="sm"
            variant="ghost"
            icon={<Square className="size-3.5" />}
            onClick={() => setGeneration((g) => g + 1)}
          />
        </Tip>
        <div className="ml-auto flex items-center gap-2">
          <Checkbox
            className="text-xs"
            checked={follow}
            onChange={(f) => {
              setFollow(f)
              localStorage.setItem('cyoa.follow', f ? '1' : '0')
            }}
            label="Follow in editor"
            title="Open each scene in the editor as you play"
          />
          <Button size="sm" variant="ghost" icon={<X className="size-4" />} onClick={onClose} aria-label="Hide playtest" />
        </div>
      </div>

      <div className="relative min-h-0 flex-1 bg-[#0b0b0e]">
        <div ref={host} className="absolute inset-0" onClick={() => term.current?.focus()} />
        {(status === 'idle' || status === 'exited' || status === 'disconnected' || status === 'connecting') && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-black/60">
            {status === 'connecting' && <div className="text-sm text-zinc-400">Connecting…</div>}
            {status === 'disconnected' && (
              <>
                <div className="text-sm text-zinc-300">Disconnected.</div>
                <Button size="sm" onClick={() => setGeneration((g) => g + 1)}>
                  Reconnect
                </Button>
              </>
            )}
            {(status === 'idle' || status === 'exited') && (
              <>
                {status === 'exited' && <div className="text-sm text-zinc-400">The game was closed.</div>}
                <div className="flex gap-2">
                  <Button variant="primary" icon={<Play className="size-3.5" />} onClick={() => start(meta?.start_scene)}>
                    Start a new game
                  </Button>
                  <Button icon={<Home className="size-3.5" />} onClick={() => start()}>
                    Title screen
                  </Button>
                </div>
              </>
            )}
          </div>
        )}
      </div>

      {error && (
        <div className="flex items-center gap-2 border-t border-red-500/30 bg-red-500/10 px-3 py-1.5 text-xs text-red-300">
          <TriangleAlert className="size-3.5" /> {error}
          <button type="button" className="ml-auto text-red-200 hover:text-white" onClick={() => setError(null)}>
            <X className="size-3.5" />
          </button>
        </div>
      )}

      <div className="border-t border-surface-700">
        <button
          type="button"
          onClick={() => setShowState((s) => !s)}
          className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs font-semibold tracking-wide text-zinc-400 uppercase hover:text-zinc-200"
        >
          {showState ? <ChevronDown className="size-3" /> : <ChevronUp className="size-3" />}
          Game state
          {currentScene && (
            <span className="truncate font-normal normal-case text-zinc-500">
              — in “{currentScene.title || currentScene.id}”
            </span>
          )}
          {problems.length > 0 && (
            <span className="ml-auto flex items-center gap-1 font-normal normal-case text-amber-400">
              <TriangleAlert className="size-3" /> {problems.length}
            </span>
          )}
        </button>
        {showState && (
          <div className="max-h-72 overflow-y-auto px-3 pb-3">
            {!state ? (
              <div className="text-xs text-zinc-500">Start playing to see variables and inventory here.</div>
            ) : (
              <StateView
                gameId={gameId}
                state={state}
                problems={problems}
                onSetVar={(name, value) => {
                  term.current?.reset()
                  send({ type: 'set_var', name, value })
                }}
                onItems={(item, amount) => {
                  term.current?.reset()
                  send({ type: 'items', item, amount })
                }}
                onGoto={(scene) => {
                  term.current?.reset()
                  send({ type: 'goto', scene })
                }}
                onOpenScene={() => currentScene && navigate(`/games/${gameId}/scenes/${currentScene.pk}`)}
              />
            )}
          </div>
        )}
      </div>
    </div>
  )
}

function StateView({
  gameId,
  state,
  problems,
  onSetVar,
  onItems,
  onGoto,
  onOpenScene,
}: {
  gameId: string
  state: PlaytestState
  problems: string[]
  onSetVar: (name: string, value: string) => void
  onItems: (item: string, amount: number) => void
  onGoto: (scene: string) => void
  onOpenScene: () => void
}) {
  const meta = useMeta(gameId)
  const scenes = useScenes(gameId)
  const [addItem, setAddItem] = useState('')
  const [jump, setJump] = useState('')
  if (!meta) return null
  return (
    <div className="flex flex-col gap-3 text-xs">
      {problems.length > 0 && (
        <ul className="flex flex-col gap-1 rounded border border-amber-500/30 bg-amber-500/10 px-2 py-1.5 text-amber-200">
          {problems.map((p) => (
            <li key={p}>{p}</li>
          ))}
        </ul>
      )}
      <div className="flex items-center gap-2">
        <button type="button" onClick={onOpenScene} className="font-mono text-accent-300 hover:underline">
          {state.scene}
        </button>
        <span className="text-zinc-600">·</span>
        <span className="text-zinc-500">{state.steps} choices made</span>
        <div className="ml-auto flex items-center gap-1">
          <Select className="h-6 w-40 text-xs" value={jump} onChange={(e) => setJump(e.target.value)}>
            <option value="">Jump to scene…</option>
            {scenes.map((s) => (
              <option key={s.pk} value={s.id}>
                {s.title || s.id}
              </option>
            ))}
          </Select>
          <Button size="xs" disabled={!jump} onClick={() => onGoto(jump)}>
            Go
          </Button>
        </div>
      </div>
      {meta.variables.length > 0 && (
        <table className="w-full">
          <tbody>
            {meta.variables.map((v) => (
              <VariableRow key={v.name} name={v.name} label={v.label} value={state.vars[v.name]} type={v.type} onSet={onSetVar} />
            ))}
          </tbody>
        </table>
      )}
      <div className="flex flex-col gap-1">
        <div className="font-medium text-zinc-400">Inventory</div>
        {Object.keys(state.inventory).length === 0 && <div className="text-zinc-600">empty</div>}
        {Object.entries(state.inventory).map(([item, count]) => {
          const spec = meta.items.find((i) => i.id === item)
          return (
            <div key={item} className="flex items-center gap-2">
              <span className="flex-1 text-zinc-300">
                {spec?.name || item} <span className="text-zinc-500">×{count}</span>
              </span>
              <Button size="xs" variant="ghost" icon={<Minus className="size-3" />} onClick={() => onItems(item, -1)} aria-label="Remove one" />
              <Button size="xs" variant="ghost" icon={<Plus className="size-3" />} onClick={() => onItems(item, 1)} aria-label="Add one" />
            </div>
          )
        })}
        {meta.items.length > 0 && (
          <div className="mt-1 flex items-center gap-1">
            <Select className="h-6 flex-1 text-xs" value={addItem} onChange={(e) => setAddItem(e.target.value)}>
              <option value="">Give item…</option>
              {meta.items.map((i) => (
                <option key={i.id} value={i.id}>
                  {i.name || i.id}
                </option>
              ))}
            </Select>
            <Button size="xs" disabled={!addItem} onClick={() => onItems(addItem, 1)}>
              Give
            </Button>
          </div>
        )}
      </div>
    </div>
  )
}

function VariableRow({
  name,
  label,
  value,
  type,
  onSet,
}: {
  name: string
  label: string
  value: Value | undefined
  type: string
  onSet: (name: string, value: string) => void
}) {
  const [draft, setDraft] = useState(String(value ?? ''))
  useEffect(() => setDraft(String(value ?? '')), [value])
  const commit = () => {
    if (draft !== String(value ?? '')) onSet(name, draft)
  }
  return (
    <tr>
      <td className="py-0.5 pr-2 text-zinc-400">
        {label || name} {label && <span className="font-mono text-zinc-600">{name}</span>}
      </td>
      <td className="w-32 py-0.5">
        {type === 'bool' ? (
          <Select className="h-6 text-xs" value={String(value)} onChange={(e) => onSet(name, e.target.value)}>
            <option value="true">true</option>
            <option value="false">false</option>
          </Select>
        ) : (
          <Input
            className={cx('h-6 text-xs', type === 'number' && 'font-mono')}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={commit}
            onKeyDown={(e) => e.key === 'Enter' && commit()}
          />
        )}
      </td>
    </tr>
  )
}
