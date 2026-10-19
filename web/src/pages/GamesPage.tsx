import { useQueryClient } from '@tanstack/react-query'
import { BookOpen, Copy, Download, FileUp, MoreHorizontal, Plus, Trash2 } from 'lucide-react'
import { useRef, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router'
import { AppHeader } from '@/components/AppHeader'
import {
  Button,
  Dialog,
  Empty,
  Input,
  Menu,
  MenuContent,
  MenuItem,
  MenuSeparator,
  MenuTrigger,
  Spinner,
} from '@/components/ui'
import { api } from '@/lib/api'
import { downloadFile, plural, relativeTime } from '@/lib/format'
import { useGames } from '@/lib/queries'
import type { GameSummary } from '@/lib/types'

export function GamesPage() {
  const games = useGames()
  const qc = useQueryClient()
  const navigate = useNavigate()
  const [creating, setCreating] = useState(false)
  const [title, setTitle] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [toDelete, setToDelete] = useState<GameSummary | null>(null)
  const fileInput = useRef<HTMLInputElement>(null)

  async function create(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    try {
      const game = await api.createGame(title.trim() || 'Untitled')
      qc.setQueryData(['game', game.id], game)
      await qc.invalidateQueries({ queryKey: ['games'] })
      navigate(`/games/${game.id}`)
    } finally {
      setBusy(false)
    }
  }

  async function importFile(file: File) {
    setError(null)
    try {
      const data = JSON.parse(await file.text())
      const game = await api.importGame(data)
      qc.setQueryData(['game', game.id], game)
      await qc.invalidateQueries({ queryKey: ['games'] })
      navigate(`/games/${game.id}`)
    } catch (err) {
      setError(
        err instanceof SyntaxError
          ? `${file.name} isn't valid JSON`
          : `Import failed: ${err instanceof Error ? err.message : String(err)}`,
      )
    }
  }

  async function duplicate(game: GameSummary) {
    await api.duplicateGame(game.id)
    await qc.invalidateQueries({ queryKey: ['games'] })
  }

  async function remove(game: GameSummary) {
    await api.deleteGame(game.id)
    setToDelete(null)
    await qc.invalidateQueries({ queryKey: ['games'] })
  }

  return (
    <div className="flex h-full flex-col">
      <AppHeader />
      <main className="mx-auto w-full max-w-5xl flex-1 overflow-y-auto px-4 py-6 sm:px-6 sm:py-8">
        <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
          <h1 className="text-xl font-semibold text-zinc-100">Your games</h1>
          <div className="flex gap-2">
            <input
              ref={fileInput}
              type="file"
              accept=".json,application/json"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0]
                if (file) void importFile(file)
                e.target.value = ''
              }}
            />
            <Button icon={<FileUp className="size-4" />} onClick={() => fileInput.current?.click()}>
              Import
            </Button>
            <Button variant="primary" icon={<Plus className="size-4" />} onClick={() => setCreating(true)}>
              New game
            </Button>
          </div>
        </div>
        {error && (
          <div className="mb-4 rounded-md border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-300">
            {error}
          </div>
        )}
        {games.isLoading ? (
          <Spinner />
        ) : games.data?.length === 0 ? (
          <Empty icon={<BookOpen className="size-10" />} title="No games yet">
            Create a new game, or import a project file exported from this dashboard.
          </Empty>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {games.data?.map((game) => (
              <div
                key={game.id}
                className="group relative flex flex-col rounded-lg border border-surface-700 bg-surface-900 transition-colors hover:border-surface-600"
              >
                <Link to={`/games/${game.id}`} className="flex flex-1 flex-col gap-1 p-4">
                  <div className="truncate pr-8 font-medium text-zinc-100">{game.title || 'Untitled'}</div>
                  {game.author && <div className="truncate text-sm text-zinc-500">by {game.author}</div>}
                  <div className="mt-3 flex gap-3 text-xs text-zinc-500">
                    <span>{plural(game.scenes, 'scene')}</span>
                    <span>{plural(game.words, 'word')}</span>
                    <span className="ml-auto">{relativeTime(game.updated_at)}</span>
                  </div>
                </Link>
                <div className="absolute top-3 right-3">
                  <Menu>
                    <MenuTrigger asChild>
                      <Button variant="ghost" size="sm" icon={<MoreHorizontal className="size-4" />} aria-label="Game actions" />
                    </MenuTrigger>
                    <MenuContent>
                      <MenuItem icon={<Copy className="size-3.5" />} onSelect={() => void duplicate(game)}>
                        Duplicate
                      </MenuItem>
                      <MenuItem
                        icon={<Download className="size-3.5" />}
                        onSelect={() => void downloadFile(api.exportUrl(game.id, 'project'))}
                      >
                        Export project backup
                      </MenuItem>
                      <MenuSeparator />
                      <MenuItem danger icon={<Trash2 className="size-3.5" />} onSelect={() => setToDelete(game)}>
                        Move to trash
                      </MenuItem>
                    </MenuContent>
                  </Menu>
                </div>
              </div>
            ))}
          </div>
        )}
      </main>

      <Dialog
        open={creating}
        onOpenChange={setCreating}
        title="New game"
        footer={
          <>
            <Button onClick={() => setCreating(false)}>Cancel</Button>
            <Button variant="primary" loading={busy} onClick={create}>
              Create
            </Button>
          </>
        }
      >
        <form onSubmit={create}>
          <Input autoFocus placeholder="Title" value={title} onChange={(e) => setTitle(e.target.value)} />
        </form>
      </Dialog>

      <Dialog
        open={toDelete !== null}
        onOpenChange={(open) => !open && setToDelete(null)}
        title={`Move “${toDelete?.title}” to the trash?`}
        description="You can restore it from the trash later."
        footer={
          <>
            <Button onClick={() => setToDelete(null)}>Cancel</Button>
            <Button variant="danger" onClick={() => toDelete && void remove(toDelete)}>
              Move to trash
            </Button>
          </>
        }
      />
    </div>
  )
}
