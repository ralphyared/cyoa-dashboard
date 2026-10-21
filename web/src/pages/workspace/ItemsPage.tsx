import { Package, Plus, Trash2 } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Button, Checkbox, Empty, Field, Input, Textarea, cx, useReadOnly } from '@/components/ui'
import { slugError, slugify } from '@/lib/format'
import { useGameActions, useMeta } from '@/lib/queries'
import type { Item } from '@/lib/types'
import { useWorkspace } from './context'
import { ConfirmDelete, PageShell, RenameButton, UnusedBadge, UsagePopover, useUnused } from './shared'

export function ItemsPage() {
  const { gameId } = useWorkspace()
  const meta = useMeta(gameId)
  const actions = useGameActions(gameId)
  const unused = useUnused('item')
  const [name, setName] = useState('')
  const [id, setId] = useState('')
  const [idEdited, setIdEdited] = useState(false)
  const [deleting, setDeleting] = useState<Item | null>(null)
  const readOnly = useReadOnly()
  if (!meta) return null
  const items = meta.items
  const ids = items.map((i) => i.id)
  const newId = idEdited ? id : slugify(name, '')
  const idError = name || idEdited ? slugError(newId, ids) : null

  const save = (next: Item[]) => actions.updateMeta({ items: next })
  const change = (index: number, changes: Partial<Item>) =>
    save(items.map((item, i) => (i === index ? { ...item, ...changes } : item)))

  function add(e: FormEvent) {
    e.preventDefault()
    if (!newId || idError) return
    save([...items, { id: newId, name: name.trim(), description: '', stackable: false }])
    setName('')
    setId('')
    setIdEdited(false)
  }

  return (
    <PageShell
      title="Items"
      description={
        <>
          Things the player can carry. Check for them with <code className="text-accent-300">has("rope")</code>,
          give and take them in effects. Stackable items have a quantity (arrows, coins…); others are
          either carried or not. Players see names and descriptions on the inventory screen.
        </>
      }
    >
      {items.length === 0 ? (
        <Empty icon={<Package className="size-10" />} title="No items yet" />
      ) : (
        <div className="flex flex-col gap-2">
          {items.map((item, i) => (
            <div key={item.id} className="flex flex-col gap-2 rounded-lg border border-surface-700 bg-surface-900 p-3 sm:flex-row sm:items-start">
              <div className="flex shrink-0 flex-row items-center gap-2 sm:w-48 sm:flex-col sm:items-start sm:gap-1">
                <RenameButton kind="item" current={item.id} taken={ids} />
                {unused.has(item.id) && <UnusedBadge />}
              </div>
              <div className="flex min-w-0 flex-1 flex-col gap-2">
                <Input value={item.name} placeholder="Name shown to players" onChange={(e) => change(i, { name: e.target.value })} />
                <Textarea
                  rows={2}
                  value={item.description}
                  placeholder="Description (shown on the inventory screen)"
                  onChange={(e) => change(i, { description: e.target.value })}
                />
              </div>
              <div className="flex shrink-0 flex-row items-center justify-between gap-2 sm:flex-col sm:items-end">
                <Checkbox checked={item.stackable} onChange={(stackable) => change(i, { stackable })} label="Stackable" />
                <div className="flex">
                  <UsagePopover kind="item" name={item.id} />
                  {!readOnly && (
                    <Button size="xs" variant="ghost" icon={<Trash2 className="size-3.5" />} aria-label="Delete" onClick={() => setDeleting(item)} />
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      <form onSubmit={add} className={cx('flex flex-wrap items-start gap-2', readOnly && 'hidden')}>
        <Input className="w-full sm:w-56" placeholder="New item name, e.g. Rusty key" value={name} onChange={(e) => setName(e.target.value)} />
        <Field error={idError} className="w-40 sm:w-48">
          <Input
            className="font-mono"
            placeholder="id"
            value={newId}
            onChange={(e) => {
              setIdEdited(true)
              setId(e.target.value.toLowerCase())
            }}
          />
        </Field>
        <Button type="submit" icon={<Plus className="size-4" />} disabled={!newId || !!idError}>
          Add item
        </Button>
      </form>

      <ConfirmDelete
        open={deleting !== null}
        onOpenChange={(o) => !o && setDeleting(null)}
        title={`Delete item “${deleting?.name || deleting?.id}”?`}
        description={
          deleting && !unused.has(deleting.id)
            ? 'It is still used somewhere; those places will show errors until you fix them.'
            : undefined
        }
        onConfirm={() => deleting && save(items.filter((x) => x.id !== deleting.id))}
      />
    </PageShell>
  )
}
