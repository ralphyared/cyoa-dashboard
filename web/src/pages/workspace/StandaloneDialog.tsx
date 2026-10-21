import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Apple, Download, Monitor, RefreshCw, Terminal } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router'
import { IssueList } from '@/components/IssueList'
import { Button, Dialog, Spinner } from '@/components/ui'
import { api } from '@/lib/api'
import { downloadFile, relativeTime } from '@/lib/format'
import { useAccess, useScenes } from '@/lib/queries'
import type { Issue } from '@/lib/types'
import { useWorkspace } from './context'
import { issueLink } from './Workspace'

const PLATFORMS: { key: string; label: string; icon: ReactNode; gets: string; note: string }[] = [
  {
    key: 'windows',
    label: 'Windows',
    icon: <Monitor className="size-5" />,
    gets: 'One .exe file. Players double-click it to play.',
    note: 'Windows may warn about an unknown publisher: click “More info”, then “Run anyway”.',
  },
  {
    key: 'macos-arm64',
    label: 'macOS (Apple Silicon)',
    icon: <Apple className="size-5" />,
    gets: 'A zip with the game and its player. Unzip, then double-click the game.',
    note: 'The first time, players allow it in System Settings → Privacy & Security → “Open Anyway” (instructions included).',
  },
  {
    key: 'macos-x64',
    label: 'macOS (Intel)',
    icon: <Apple className="size-5" />,
    gets: 'Same as Apple Silicon, for Macs from before 2021.',
    note: 'Same first-time step as above.',
  },
  {
    key: 'linux',
    label: 'Linux',
    icon: <Terminal className="size-5" />,
    gets: 'One program inside a .tar.gz. Extract it and run it in a terminal.',
    note: '',
  },
]

export function StandaloneDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const { gameId, setPanel } = useWorkspace()
  const scenes = useScenes(gameId)
  const navigate = useNavigate()
  const qc = useQueryClient()
  const status = useQuery({ queryKey: ['players'], queryFn: api.players, enabled: open })
  const [busy, setBusy] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [issues, setIssues] = useState<Issue[] | null>(null)
  const [updating, setUpdating] = useState(false)
  const isOwner = useAccess(gameId) === 'owner'

  async function exportFor(platform: string) {
    setBusy(platform)
    setMessage(null)
    setIssues(null)
    try {
      await downloadFile(api.standaloneUrl(gameId, platform))
      void qc.invalidateQueries({ queryKey: ['players'] })
    } catch (e) {
      const detail = (e as { detail?: { message?: string; issues?: Issue[] } | string }).detail
      if (detail && typeof detail === 'object' && detail.issues) setIssues(detail.issues)
      else if (detail && typeof detail === 'object' && detail.message) setMessage(detail.message)
      else setMessage(typeof detail === 'string' ? detail : 'The export failed.')
    } finally {
      setBusy(null)
    }
  }

  async function update() {
    setUpdating(true)
    setMessage(null)
    try {
      qc.setQueryData(['players'], await api.updatePlayers())
    } catch (e) {
      setMessage(e instanceof Error ? e.message : String(e))
    } finally {
      setUpdating(false)
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      wide
      title="Export a ready-to-play game"
      description="A download your players can run right away, no setup needed. Pick their system."
      footer={<Button onClick={() => onOpenChange(false)}>Close</Button>}
    >
      <div className="flex flex-col gap-4">
        <div className="grid gap-2 sm:grid-cols-2">
          {PLATFORMS.map((p) => (
            <button
              key={p.key}
              type="button"
              disabled={busy !== null}
              onClick={() => void exportFor(p.key)}
              className="flex flex-col gap-1.5 rounded-lg border border-surface-600 bg-surface-900 p-3 text-left transition-colors hover:border-accent-600 disabled:opacity-60"
            >
              <div className="flex items-center gap-2 font-medium text-zinc-100">
                {p.icon}
                {p.label}
                <span className="ml-auto text-accent-400">
                  {busy === p.key ? <Spinner className="text-accent-400" /> : <Download className="size-4" />}
                </span>
              </div>
              <div className="text-sm text-zinc-400">{p.gets}</div>
              {p.note && <div className="text-xs text-zinc-500">{p.note}</div>}
            </button>
          ))}
        </div>
        {busy && (
          <div className="text-xs text-zinc-500">
            Preparing the download… the first export after a new player release also fetches the
            player, which can take a little while.
          </div>
        )}
        {message && (
          <div className="rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm text-amber-200">
            {message}
          </div>
        )}
        {issues && (
          <div className="flex flex-col gap-2">
            <div className="text-sm text-red-300">Fix these errors first; players can't safely play a game with errors:</div>
            <IssueList issues={issues} />
            <div>
              <Button
                size="sm"
                onClick={() => {
                  onOpenChange(false)
                  setPanel('issues')
                  const link = issueLink(issues[0], gameId, scenes)
                  if (link) navigate(link)
                }}
              >
                Show me
              </Button>
            </div>
          </div>
        )}
        <div className="flex items-center gap-2 border-t border-surface-700 pt-3 text-xs text-zinc-500">
          {status.isLoading ? (
            <Spinner />
          ) : status.data?.version ? (
            <span>
              Player version <span className="font-mono text-zinc-300">{status.data.version.replace('player-', '')}</span>
              {status.data.checked_at && <> · checked {relativeTime(status.data.checked_at)}</>}
            </span>
          ) : (
            <span>The player is fetched from GitHub the first time you export.</span>
          )}
          {isOwner && (
            <Button className="ml-auto" size="xs" variant="ghost" icon={<RefreshCw className="size-3" />} loading={updating} onClick={() => void update()}>
              Check for a newer player
            </Button>
          )}
        </div>
      </div>
    </Dialog>
  )
}
