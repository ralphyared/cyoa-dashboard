import { useQuery, useQueryClient } from '@tanstack/react-query'
import { KeyRound, Trash2, Users } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'
import { AppHeader } from '@/components/AppHeader'
import { Badge, Button, Dialog, Empty, Spinner } from '@/components/ui'
import { api } from '@/lib/api'
import { relativeTime } from '@/lib/format'
import { LEVELS, errorText, expiresText } from '@/lib/sharing'
import type { Person } from '@/lib/types'
import { CopyLink } from './workspace/ShareDialog'

/** Everyone with an account (the owner only). Sharing itself happens from each game's Share button. */
export function PeoplePage() {
  const qc = useQueryClient()
  const people = useQuery({ queryKey: ['people'], queryFn: api.people })
  const [removing, setRemoving] = useState<Person | null>(null)
  const [link, setLink] = useState<{ username: string; url: string; expires: string } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const guests = (people.data ?? []).filter((p) => !p.owner)

  async function resetLink(person: Person) {
    setError(null)
    try {
      const reset = await api.resetLink(person.id)
      setLink({
        username: reset.username,
        url: `${window.location.origin}/reset/${reset.token}`,
        expires: expiresText(reset.expires_at),
      })
    } catch (err) {
      setError(errorText(err))
    }
  }

  async function remove(person: Person) {
    setError(null)
    try {
      await api.removePerson(person.id)
      setRemoving(null)
      await Promise.all([
        qc.invalidateQueries({ queryKey: ['people'] }),
        qc.invalidateQueries({ queryKey: ['games'] }),
        qc.invalidateQueries({ queryKey: ['sharing'] }),
      ])
    } catch (err) {
      setError(errorText(err))
    }
  }

  return (
    <div className="flex h-full flex-col">
      <AppHeader />
      <main className="mx-auto w-full max-w-3xl flex-1 overflow-y-auto px-4 py-6 sm:px-6 sm:py-8">
        <h1 className="mb-2 text-xl font-semibold text-zinc-100">People</h1>
        <p className="mb-6 text-sm text-zinc-500">
          Everyone you've shared a game with. To share a game, or change what someone can do with it,
          open the game and use “Share”.
        </p>
        {error && (
          <div className="mb-4 rounded-md border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-300">{error}</div>
        )}
        {people.isLoading && <Spinner />}
        {people.data && guests.length === 0 && (
          <Empty icon={<Users className="size-10" />} title="Nobody yet">
            Open a game and use “Share” to invite someone.
          </Empty>
        )}
        <div className="flex flex-col gap-2">
          {guests.map((person) => (
            <div key={person.id} className="flex flex-col gap-2 rounded-lg border border-surface-700 bg-surface-900 p-3">
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                <span className="font-medium text-zinc-100">{person.username}</span>
                <span className="text-xs text-zinc-500">
                  joined {relativeTime(person.created_at)}
                  {person.last_login_at && <> · last logged in {relativeTime(person.last_login_at)}</>}
                </span>
                <div className="ml-auto flex gap-1">
                  <Button size="sm" variant="ghost" icon={<KeyRound className="size-3.5" />} onClick={() => void resetLink(person)}>
                    Password link
                  </Button>
                  <Button size="sm" variant="ghost" icon={<Trash2 className="size-3.5" />} onClick={() => setRemoving(person)}>
                    Remove
                  </Button>
                </div>
              </div>
              {person.games.length === 0 ? (
                <div className="text-xs text-zinc-500">No games shared with them right now.</div>
              ) : (
                <ul className="flex flex-wrap gap-1.5">
                  {person.games.map((game) => (
                    <li key={game.id}>
                      <Link
                        to={`/games/${game.id}`}
                        className="flex items-center gap-1.5 rounded-md border border-surface-700 px-2 py-1 text-xs text-zinc-300 hover:border-surface-600"
                      >
                        {game.title || 'Untitled'}
                        <Badge tone={game.level === 'edit' ? 'accent' : 'neutral'}>{LEVELS[game.level].label.toLowerCase()}</Badge>
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ))}
        </div>
      </main>

      <Dialog
        open={link !== null}
        onOpenChange={(open) => !open && setLink(null)}
        title={`Password link for ${link?.username}`}
        description="Send it to them. Opening it lets them choose a new password (and logs them out everywhere else)."
        footer={<Button onClick={() => setLink(null)}>Done</Button>}
      >
        {link && (
          <div className="flex flex-col gap-2">
            <CopyLink url={link.url} />
            <div className="text-xs text-zinc-400">
              It works once and {link.expires}. Making a new one cancels this one.
            </div>
          </div>
        )}
      </Dialog>

      <Dialog
        open={removing !== null}
        onOpenChange={(open) => !open && setRemoving(null)}
        title={`Remove ${removing?.username}?`}
        description="Their account is deleted and they lose access to every game. Changes they made stay."
        footer={
          <>
            <Button onClick={() => setRemoving(null)}>Cancel</Button>
            <Button variant="danger" onClick={() => removing && void remove(removing)}>
              Remove
            </Button>
          </>
        }
      />
    </div>
  )
}
