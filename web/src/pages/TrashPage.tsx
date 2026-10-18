import { useQuery, useQueryClient } from '@tanstack/react-query'
import { RotateCcw, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { AppHeader } from '@/components/AppHeader'
import { Button, Dialog, Empty, SectionTitle, Spinner } from '@/components/ui'
import { api } from '@/lib/api'
import { relativeTime } from '@/lib/format'

export function TrashPage() {
  const qc = useQueryClient()
  const trash = useQuery({ queryKey: ['trash'], queryFn: api.trash })
  const [purge, setPurge] = useState<{ kind: 'game' | 'scene'; id: string | number; name: string } | null>(null)

  async function refresh(gameId?: string) {
    await qc.invalidateQueries({ queryKey: ['trash'] })
    await qc.invalidateQueries({ queryKey: ['games'] })
    if (gameId) await qc.invalidateQueries({ queryKey: ['game', gameId] })
  }

  async function confirmPurge() {
    if (!purge) return
    if (purge.kind === 'game') await api.purgeGame(String(purge.id))
    else await api.purgeScene(Number(purge.id))
    setPurge(null)
    await refresh()
  }

  const empty = trash.data && trash.data.games.length === 0 && trash.data.scenes.length === 0
  return (
    <div className="flex h-full flex-col">
      <AppHeader />
      <main className="mx-auto w-full max-w-4xl flex-1 overflow-y-auto px-6 py-8">
        <h1 className="mb-6 text-xl font-semibold text-zinc-100">Trash</h1>
        {trash.isLoading && <Spinner />}
        {empty && <Empty icon={<Trash2 className="size-10" />} title="The trash is empty" />}
        {trash.data && trash.data.games.length > 0 && (
          <section className="mb-8 flex flex-col gap-2">
            <SectionTitle>Games</SectionTitle>
            {trash.data.games.map((game) => (
              <div key={game.id} className="flex items-center gap-3 rounded-md border border-surface-700 bg-surface-900 px-3 py-2">
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm text-zinc-200">{game.title}</div>
                  <div className="text-xs text-zinc-500">
                    {game.scenes} scenes · deleted {game.deleted_at ? relativeTime(game.deleted_at) : ''}
                  </div>
                </div>
                <Button size="sm" icon={<RotateCcw className="size-3.5" />} onClick={async () => {
                  await api.restoreGame(game.id)
                  await refresh(game.id)
                }}>
                  Restore
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setPurge({ kind: 'game', id: game.id, name: game.title })}>
                  Delete forever
                </Button>
              </div>
            ))}
          </section>
        )}
        {trash.data && trash.data.scenes.length > 0 && (
          <section className="flex flex-col gap-2">
            <SectionTitle>Scenes</SectionTitle>
            {trash.data.scenes.map((scene) => (
              <div key={scene.pk} className="flex items-center gap-3 rounded-md border border-surface-700 bg-surface-900 px-3 py-2">
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm text-zinc-200">
                    {scene.title || scene.id} <span className="font-mono text-xs text-zinc-500">{scene.id}</span>
                  </div>
                  <div className="text-xs text-zinc-500">
                    from {scene.game_title} · deleted {scene.deleted_at ? relativeTime(scene.deleted_at) : ''}
                  </div>
                </div>
                <Button size="sm" icon={<RotateCcw className="size-3.5" />} onClick={async () => {
                  await api.restoreScene(scene.pk)
                  await refresh(scene.game_id)
                }}>
                  Restore
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setPurge({ kind: 'scene', id: scene.pk, name: scene.title || scene.id })}>
                  Delete forever
                </Button>
              </div>
            ))}
          </section>
        )}
      </main>
      <Dialog
        open={purge !== null}
        onOpenChange={(open) => !open && setPurge(null)}
        title={`Delete “${purge?.name}” forever?`}
        description="This can't be undone (except by restoring a backup)."
        footer={
          <>
            <Button onClick={() => setPurge(null)}>Cancel</Button>
            <Button variant="danger" onClick={() => void confirmPurge()}>
              Delete forever
            </Button>
          </>
        }
      />
    </div>
  )
}
