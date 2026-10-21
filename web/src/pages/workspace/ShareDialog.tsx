import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, Copy, Link2, Plus, X } from 'lucide-react'
import { useState } from 'react'
import { Button, Dialog, Field, Input, Segmented, Select, Spinner } from '@/components/ui'
import { api } from '@/lib/api'
import { useMeta } from '@/lib/queries'
import { LEVEL_OPTIONS, LEVELS, expiresText } from '@/lib/sharing'
import type { ShareLevel } from '@/lib/types'
import { useWorkspace } from './context'

/** A link with a Copy button. */
export function CopyLink({ url }: { url: string }) {
  const [copied, setCopied] = useState(false)
  async function copy() {
    try {
      await navigator.clipboard.writeText(url)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // no clipboard access: the link is selected so it can be copied by hand
    }
  }
  return (
    <div className="flex gap-2">
      <Input readOnly value={url} className="font-mono text-xs" onFocus={(e) => e.target.select()} aria-label="Link" />
      <Button
        variant="primary"
        icon={copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
        onClick={() => void copy()}
      >
        {copied ? 'Copied' : 'Copy'}
      </Button>
    </div>
  )
}

export function ShareDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const { gameId } = useWorkspace()
  const meta = useMeta(gameId)
  const qc = useQueryClient()
  const sharing = useQuery({ queryKey: ['sharing', gameId], queryFn: () => api.sharing(gameId), enabled: open })
  const people = useQuery({ queryKey: ['people'], queryFn: api.people, enabled: open })
  const [level, setLevel] = useState<ShareLevel>('read')
  const [note, setNote] = useState('')
  const [created, setCreated] = useState<{ url: string; note: string } | null>(null)
  const [addPerson, setAddPerson] = useState('')
  const [addLevel, setAddLevel] = useState<ShareLevel>('read')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function act(action: () => Promise<unknown>) {
    setBusy(true)
    setError(null)
    try {
      await action()
      await Promise.all([
        qc.invalidateQueries({ queryKey: ['sharing', gameId] }),
        qc.invalidateQueries({ queryKey: ['people'] }),
        qc.invalidateQueries({ queryKey: ['games'] }),
      ])
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  function createLink() {
    void act(async () => {
      const invite = await api.createInvite(gameId, level, note)
      setCreated({ url: `${window.location.origin}/invite/${invite.token}`, note: invite.note })
      setNote('')
    })
  }

  const members = sharing.data?.people ?? []
  const memberIds = new Set(members.map((p) => p.user_id))
  const others = (people.data ?? []).filter((p) => !p.owner && !memberIds.has(p.id))

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        onOpenChange(o)
        if (!o) {
          setCreated(null)
          setError(null)
        }
      }}
      title={`Share “${meta?.title || 'Untitled'}”`}
      description="People see only the games you share with them. Only you can delete a game or share it."
    >
      <div className="flex flex-col gap-6">
        {error && (
          <div className="rounded-md border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-300">{error}</div>
        )}

        <section className="flex flex-col gap-2">
          <h3 className="text-xs font-semibold tracking-wide text-zinc-400 uppercase">Invite someone</h3>
          <Field label="Who is it for? (only you see this)">
            <Input value={note} maxLength={100} placeholder="e.g. Sam" onChange={(e) => setNote(e.target.value)} />
          </Field>
          <div className="flex flex-wrap items-center gap-2">
            <Segmented value={level} onChange={setLevel} options={LEVEL_OPTIONS} />
            <span className="text-xs text-zinc-500">{LEVELS[level].help}</span>
          </div>
          <div>
            <Button icon={<Link2 className="size-3.5" />} loading={busy} onClick={createLink}>
              Create invite link
            </Button>
          </div>
          {created && (
            <div className="flex flex-col gap-2 rounded-md border border-accent-600/40 bg-accent-500/10 p-3">
              <div className="text-sm text-zinc-200">
                Send this link to {created.note || 'them'} (by message, email…):
              </div>
              <CopyLink url={created.url} />
              <div className="text-xs text-zinc-400">
                It works once, for 7 days. For safety it's only shown now; you can always make another.
              </div>
            </div>
          )}
        </section>

        <section className="flex flex-col gap-2">
          <h3 className="text-xs font-semibold tracking-wide text-zinc-400 uppercase">People with access</h3>
          {sharing.isLoading && <Spinner />}
          {sharing.data && members.length === 0 && <div className="text-sm text-zinc-500">Nobody yet.</div>}
          <ul className="flex flex-col gap-1.5">
            {members.map((person) => (
              <li key={person.user_id} className="flex items-center gap-2">
                <span className="min-w-0 flex-1 truncate text-sm text-zinc-200">{person.username}</span>
                <Select
                  className="h-7 w-auto text-xs"
                  value={person.level}
                  disabled={busy}
                  aria-label={`What ${person.username} can do`}
                  onChange={(e) => void act(() => api.setLevel(gameId, person.user_id, e.target.value as ShareLevel))}
                >
                  {LEVEL_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </Select>
                <Button
                  size="sm"
                  variant="ghost"
                  icon={<X className="size-3.5" />}
                  disabled={busy}
                  onClick={() => void act(() => api.removeAccess(gameId, person.user_id))}
                >
                  Remove
                </Button>
              </li>
            ))}
          </ul>
        </section>

        {(sharing.data?.invites.length ?? 0) > 0 && (
          <section className="flex flex-col gap-2">
            <h3 className="text-xs font-semibold tracking-wide text-zinc-400 uppercase">Links not used yet</h3>
            <ul className="flex flex-col gap-1.5">
              {sharing.data?.invites.map((invite) => (
                <li key={invite.id} className="flex items-center gap-2 text-sm">
                  <span className="min-w-0 flex-1 truncate text-zinc-300">
                    {invite.note ? `For ${invite.note}` : 'Invite link'}
                    <span className="text-zinc-500">
                      {' '}
                      · {LEVELS[invite.level].label.toLowerCase()} · {expiresText(invite.expires_at)}
                    </span>
                  </span>
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={busy}
                    onClick={() => void act(() => api.cancelInvite(gameId, invite.id))}
                  >
                    Cancel link
                  </Button>
                </li>
              ))}
            </ul>
          </section>
        )}

        {others.length > 0 && (
          <section className="flex flex-col gap-2">
            <h3 className="text-xs font-semibold tracking-wide text-zinc-400 uppercase">
              Add someone who already has an account
            </h3>
            <div className="flex flex-wrap items-center gap-2">
              <Select className="w-auto min-w-40" value={addPerson} onChange={(e) => setAddPerson(e.target.value)} aria-label="Person">
                <option value="">Choose a person…</option>
                {others.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.username}
                  </option>
                ))}
              </Select>
              <Segmented value={addLevel} onChange={setAddLevel} options={LEVEL_OPTIONS} />
              <Button
                icon={<Plus className="size-3.5" />}
                disabled={!addPerson || busy}
                onClick={() =>
                  void act(async () => {
                    await api.setLevel(gameId, Number(addPerson), addLevel)
                    setAddPerson('')
                  })
                }
              >
                Add
              </Button>
            </div>
          </section>
        )}
      </div>
    </Dialog>
  )
}
