import { useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle,
  BookMarked,
  Check,
  ChevronLeft,
  CircleAlert,
  CloudOff,
  Download,
  FileJson,
  GitBranch,
  Layers,
  ListTree,
  Loader2,
  Package,
  Play,
  Settings,
  Sigma,
  Workflow,
} from 'lucide-react'
import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useState,
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
} from 'react'
import { Link, Navigate, NavLink, Outlet, useNavigate, useParams } from 'react-router'
import {
  Badge,
  Button,
  Dialog,
  Empty,
  Kbd,
  Menu,
  MenuContent,
  MenuItem,
  MenuTrigger,
  Spinner,
  Tip,
  cx,
} from '@/components/ui'
import { api, ApiError } from '@/lib/api'
import { downloadFile } from '@/lib/format'
import {
  SaveContext,
  useGame,
  useIssues,
  useMeta,
  useOverallSaveStatus,
  useScenes,
} from '@/lib/queries'
import { SaveManager } from '@/lib/save'
import type { Issue, Scene } from '@/lib/types'
import { CommandPalette } from './CommandPalette'
import { useWorkspace, WorkspaceContext, type PanelKind, type PlaytestRequest } from './context'
import { IssuesPanel, issueTitle } from './IssuesPanel'
import { Sidebar } from './Sidebar'

const PlaytestPanel = lazy(() => import('./PlaytestPanel').then((m) => ({ default: m.PlaytestPanel })))

export function Workspace() {
  const { gameId = '' } = useParams()
  const qc = useQueryClient()
  const game = useGame(gameId)
  const saver = useMemo(() => new SaveManager(qc, gameId), [qc, gameId])
  const [panel, setPanel] = useState<PanelKind | null>(null)
  const [playtestOpened, setPlaytestOpened] = useState(false)
  const [playtestRequest, setPlaytestRequest] = useState<PlaytestRequest | null>(null)
  const [paletteOpen, setPaletteOpen] = useState(false)

  useEffect(() => {
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      if (saver.hasUnsaved()) {
        void saver.flushAll()
        e.preventDefault()
      }
    }
    window.addEventListener('beforeunload', onBeforeUnload)
    return () => {
      window.removeEventListener('beforeunload', onBeforeUnload)
      void saver.flushAll()
    }
  }, [saver])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setPaletteOpen(true)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const playtest = useCallback((scene?: string) => {
    setPlaytestOpened(true)
    setPanel('playtest')
    setPlaytestRequest({ scene, nonce: Date.now() })
  }, [])

  const openPanel = useCallback((next: PanelKind | null) => {
    if (next === 'playtest') setPlaytestOpened(true)
    setPanel(next)
  }, [])

  const context = useMemo(
    () => ({
      gameId,
      panel,
      setPanel: openPanel,
      playtest,
      playtestRequest,
      openPalette: () => setPaletteOpen(true),
    }),
    [gameId, panel, openPanel, playtest, playtestRequest],
  )

  if (game.isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Spinner />
      </div>
    )
  }
  if (game.error) {
    const notFound = game.error instanceof ApiError && game.error.status === 404
    return (
      <div className="flex h-full items-center justify-center">
        <Empty title={notFound ? 'Game not found' : 'Could not load the game'}>
          <Link to="/" className="text-accent-400 hover:underline">
            Back to your games
          </Link>
        </Empty>
      </div>
    )
  }

  return (
    <SaveContext.Provider value={saver}>
      <WorkspaceContext.Provider value={context}>
        <div className="flex h-full flex-col">
          <TopBar />
          <div className="flex min-h-0 flex-1">
            <Sidebar />
            <main className="min-w-0 flex-1 overflow-hidden">
              <Outlet />
            </main>
            <RightPanel
              panel={panel}
              playtestMounted={playtestOpened}
              onClose={() => setPanel(null)}
            />
          </div>
        </div>
        <CommandPalette open={paletteOpen} onOpenChange={setPaletteOpen} />
      </WorkspaceContext.Provider>
    </SaveContext.Provider>
  )
}

export function WorkspaceHome() {
  const { gameId = '' } = useParams()
  const target = useGame(gameId, (g) => {
    const start = g.scenes.find((s) => s.id === g.meta.start_scene) ?? g.scenes[0]
    return start?.pk ?? null
  }).data
  if (target === undefined) return null
  if (target === null) {
    return <Empty title="No scenes yet">Use “New scene” in the sidebar to write your first scene.</Empty>
  }
  return <Navigate to={`scenes/${target}`} replace />
}

function NavTab({ to, icon, children }: { to: string; icon: ReactNode; children: ReactNode }) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        cx(
          'flex h-8 items-center gap-1.5 rounded-md px-2.5 text-sm transition-colors',
          isActive ? 'bg-surface-800 text-zinc-100' : 'text-zinc-400 hover:text-zinc-100',
        )
      }
    >
      {icon}
      <span className="hidden xl:inline">{children}</span>
    </NavLink>
  )
}

function SaveIndicator() {
  const status = useOverallSaveStatus()
  const map = {
    saved: { icon: <Check className="size-3.5" />, text: 'Saved', cls: 'text-zinc-500' },
    pending: { icon: <Loader2 className="size-3.5 animate-spin" />, text: 'Saving…', cls: 'text-zinc-400' },
    saving: { icon: <Loader2 className="size-3.5 animate-spin" />, text: 'Saving…', cls: 'text-zinc-400' },
    error: { icon: <CloudOff className="size-3.5" />, text: 'Not saved, retrying', cls: 'text-red-400' },
    conflict: { icon: <AlertTriangle className="size-3.5" />, text: 'Edit conflict', cls: 'text-amber-400' },
  }[status]
  return (
    <div className={cx('flex items-center gap-1.5 text-xs', map.cls)} title="Changes save automatically">
      {map.icon}
      <span className="hidden md:inline">{map.text}</span>
    </div>
  )
}

function TopBar() {
  const { gameId = '' } = useParams()
  const meta = useMeta(gameId)
  const issues = useIssues(gameId)
  const { panel, setPanel, playtest, openPalette } = useWorkspace()
  const [exportErrors, setExportErrors] = useState<Issue[] | null>(null)
  const navigate = useNavigate()
  const scenes = useScenes(gameId)
  const scenePk = useGame(gameId, (g) => {
    const start = g.scenes.find((s) => s.id === g.meta.start_scene) ?? g.scenes[0]
    return start?.pk
  }).data

  const errors = issues.data?.issues.filter((i) => i.severity === 'error').length ?? 0
  const warnings = issues.data?.issues.filter((i) => i.severity === 'warning').length ?? 0

  async function exportPlayer() {
    try {
      await downloadFile(api.exportUrl(gameId, 'player'))
    } catch (e) {
      const detail = (e as { detail?: { issues?: Issue[] } }).detail
      setExportErrors(detail?.issues ?? [])
    }
  }

  return (
    <header className="flex h-12 shrink-0 items-center gap-2 border-b border-surface-700 bg-surface-900 px-3">
      <Tip content="All games">
        <Link to="/" className="flex size-8 items-center justify-center rounded-md text-zinc-400 hover:bg-surface-800 hover:text-zinc-100">
          <ChevronLeft className="size-4" />
        </Link>
      </Tip>
      <div className="max-w-56 truncate font-semibold text-zinc-100" title={meta?.title}>
        {meta?.title || 'Untitled'}
      </div>
      <nav className="ml-3 flex items-center gap-0.5">
        <NavTab to={scenePk ? `scenes/${scenePk}` : '.'} icon={<ListTree className="size-4" />}>
          Scenes
        </NavTab>
        <NavTab to="graph" icon={<Workflow className="size-4" />}>
          Graph
        </NavTab>
        <NavTab to="variables" icon={<Sigma className="size-4" />}>
          Variables
        </NavTab>
        <NavTab to="items" icon={<Package className="size-4" />}>
          Items
        </NavTab>
        <NavTab to="rules" icon={<GitBranch className="size-4" />}>
          Rules
        </NavTab>
        <NavTab to="chapters" icon={<Layers className="size-4" />}>
          Chapters
        </NavTab>
        <NavTab to="settings" icon={<Settings className="size-4" />}>
          Settings
        </NavTab>
        <NavTab to="reference" icon={<BookMarked className="size-4" />}>
          Help
        </NavTab>
      </nav>
      <div className="ml-auto flex items-center gap-2">
        <button
          type="button"
          onClick={openPalette}
          className="hidden items-center gap-2 rounded-md border border-surface-700 px-2 py-1 text-xs text-zinc-500 hover:text-zinc-300 lg:flex"
        >
          Jump to… <Kbd>Ctrl K</Kbd>
        </button>
        <SaveIndicator />
        <Button
          size="sm"
          variant={panel === 'issues' ? 'secondary' : 'ghost'}
          onClick={() => setPanel(panel === 'issues' ? null : 'issues')}
          title="Problems in the game"
        >
          {errors > 0 && (
            <Badge tone="error">
              <CircleAlert className="size-3" />
              {errors}
            </Badge>
          )}
          {warnings > 0 && (
            <Badge tone="warning">
              <AlertTriangle className="size-3" />
              {warnings}
            </Badge>
          )}
          {errors === 0 && warnings === 0 && (
            <span className="flex items-center gap-1 text-emerald-400">
              <Check className="size-3.5" /> No issues
            </span>
          )}
        </Button>
        <Button
          size="sm"
          variant={panel === 'playtest' ? 'secondary' : 'primary'}
          icon={<Play className="size-3.5" />}
          onClick={() => (panel === 'playtest' ? setPanel(null) : playtest())}
        >
          Playtest
        </Button>
        <Menu>
          <MenuTrigger asChild>
            <Button size="sm" icon={<Download className="size-3.5" />}>
              Export
            </Button>
          </MenuTrigger>
          <MenuContent>
            <MenuItem icon={<Play className="size-3.5" />} onSelect={() => void exportPlayer()}>
              Game file for players (.cyoa.json)
            </MenuItem>
            <MenuItem
              icon={<FileJson className="size-3.5" />}
              onSelect={() => void downloadFile(api.exportUrl(gameId, 'project'))}
            >
              Project backup (with notes)
            </MenuItem>
          </MenuContent>
        </Menu>
      </div>
      <Dialog
        open={exportErrors !== null}
        onOpenChange={(open) => !open && setExportErrors(null)}
        title="Fix these errors before exporting"
        description="Players can't safely play a game with errors. Warnings are fine."
        footer={<Button onClick={() => setExportErrors(null)}>Close</Button>}
      >
        <ul className="flex flex-col gap-1.5">
          {exportErrors?.map((issue, i) => (
            <li key={i}>
              <button
                type="button"
                className="w-full rounded px-2 py-1.5 text-left text-sm hover:bg-surface-800"
                onClick={() => {
                  setExportErrors(null)
                  setPanel('issues')
                  navigate(issueLink(issue, gameId, scenes) ?? '.')
                }}
              >
                <div className="text-zinc-200">{issue.message}</div>
                <div className="text-xs text-zinc-500">{issueTitle(issue)}</div>
              </button>
            </li>
          ))}
        </ul>
      </Dialog>
    </header>
  )
}

/** Where to go to fix an issue (the scene editor, or the relevant table). */
export function issueLink(issue: Issue, gameId: string, scenes: Scene[]): string | null {
  const base = `/games/${gameId}`
  const scene = issue.scene ? scenes.find((s) => s.id === issue.scene) : undefined
  if (scene) return `${base}/scenes/${scene.pk}`
  if (issue.rule) return `${base}/rules`
  if (issue.variable) return `${base}/variables`
  if (issue.item) return `${base}/items`
  if (issue.chapter) return `${base}/chapters`
  if (issue.field === 'status_format' || issue.field === 'intro' || issue.field === 'start_scene') {
    return `${base}/settings`
  }
  return null
}

function RightPanel({
  panel,
  playtestMounted,
  onClose,
}: {
  panel: PanelKind | null
  playtestMounted: boolean
  onClose: () => void
}) {
  const [width, setWidth] = useState(() => Number(localStorage.getItem('cyoa.panelWidth')) || 560)
  useEffect(() => localStorage.setItem('cyoa.panelWidth', String(width)), [width])

  function startResize(e: ReactPointerEvent) {
    e.preventDefault()
    const startX = e.clientX
    const startWidth = width
    const move = (ev: PointerEvent) =>
      setWidth(Math.min(Math.max(320, startWidth + startX - ev.clientX), window.innerWidth - 400))
    const up = () => {
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', up)
    }
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', up)
  }

  if (!panel && !playtestMounted) return null
  return (
    <aside
      className={cx('relative flex shrink-0 flex-col border-l border-surface-700 bg-surface-900', !panel && 'hidden')}
      style={{ width }}
    >
      <div
        onPointerDown={startResize}
        className="absolute inset-y-0 -left-1 z-10 w-2 cursor-col-resize hover:bg-accent-500/30"
      />
      {panel === 'issues' && <IssuesPanel onClose={onClose} />}
      {playtestMounted && (
        <div className={cx('flex min-h-0 flex-1 flex-col', panel !== 'playtest' && 'hidden')}>
          <Suspense fallback={<Spinner className="m-4" />}>
            <PlaytestPanel onClose={onClose} visible={panel === 'playtest'} />
          </Suspense>
        </div>
      )}
    </aside>
  )
}
