import { useQuery } from '@tanstack/react-query'
import { Link2, Pencil } from 'lucide-react'
import { useEffect, useState, type ReactNode } from 'react'
import { Link } from 'react-router'
import {
  Badge,
  Button,
  Dialog,
  Field,
  Input,
  Popover,
  PopoverContent,
  PopoverTrigger,
  Spinner,
} from '@/components/ui'
import { api } from '@/lib/api'
import { slugError, variableNameError } from '@/lib/format'
import { useGameActions, useIssues, useScenes } from '@/lib/queries'
import type { RefKind } from '@/lib/types'
import { useWorkspace } from './context'

export function PageShell({
  title,
  description,
  actions,
  children,
}: {
  title: string
  description?: ReactNode
  actions?: ReactNode
  children: ReactNode
}) {
  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto flex max-w-5xl flex-col gap-5 px-4 py-4 sm:px-6 sm:py-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-xl font-semibold text-zinc-100">{title}</h1>
            {description && <p className="mt-1 max-w-2xl text-sm text-zinc-500">{description}</p>}
          </div>
          {actions}
        </div>
        {children}
      </div>
    </div>
  )
}

const FIELD_LABELS: Record<string, string> = {
  text: 'text',
  choice_text: 'choice text',
  condition: 'condition',
  effects: 'effects',
  on_enter: 'arrival effects',
  status_format: 'status bar',
  intro: 'intro',
  target: 'choice destination',
  goto: 'rule destination',
  start_scene: 'start scene',
  min: 'minimum',
  max: 'maximum',
  chapter: 'chapter',
}

/** "Used in N places" with a popover listing them. */
export function UsagePopover({ kind, name, compact }: { kind: RefKind; name: string; compact?: boolean }) {
  const { gameId } = useWorkspace()
  const scenes = useScenes(gameId)
  const [open, setOpen] = useState(false)
  const refs = useQuery({
    queryKey: ['refs', gameId, kind, name],
    queryFn: () => api.references(gameId, kind, name),
    enabled: open,
    staleTime: 0,
  })
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button size="xs" variant="ghost" icon={<Link2 className="size-3" />} title="Where is this used?">
          {compact ? null : 'Where used'}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-80 p-2" align="end">
        {refs.isLoading && <Spinner />}
        {refs.data && refs.data.references.length === 0 && (
          <div className="px-1 py-2 text-sm text-zinc-500">Not used anywhere yet.</div>
        )}
        <ul className="max-h-72 overflow-y-auto">
          {refs.data?.references.map((ref, i) => {
            const scene = ref.scene ? scenes.find((s) => s.id === ref.scene) : undefined
            const where = FIELD_LABELS[ref.field] ?? ref.field
            const to = scene
              ? `/games/${gameId}/scenes/${scene.pk}${ref.choice ? `?choice=${ref.choice}` : ''}`
              : ref.rule
                ? `/games/${gameId}/rules`
                : ref.variable
                  ? `/games/${gameId}/variables`
                  : `/games/${gameId}/settings`
            return (
              <li key={i}>
                <Link to={to} onClick={() => setOpen(false)} className="block rounded px-2 py-1 text-sm hover:bg-surface-700">
                  <span className="text-zinc-200">
                    {scene ? scene.title || scene.id : ref.rule ? 'Rule' : ref.variable ? `Variable ${ref.variable}` : 'Settings'}
                  </span>{' '}
                  <span className="text-xs text-zinc-500">{where}</span>
                </Link>
              </li>
            )
          })}
        </ul>
      </PopoverContent>
    </Popover>
  )
}

export function useUnused(kind: 'variable' | 'item'): Set<string> {
  const { gameId } = useWorkspace()
  const issues = useIssues(gameId).data?.issues ?? []
  const code = kind === 'variable' ? 'unused_variable' : 'unused_item'
  return new Set(issues.filter((i) => i.code === code).map((i) => (kind === 'variable' ? i.variable : i.item) ?? ''))
}

export function UnusedBadge() {
  return (
    <Badge tone="warning" title="Not used anywhere yet">
      unused
    </Badge>
  )
}

export function RenameButton({
  kind,
  current,
  taken,
}: {
  kind: 'variable' | 'item' | 'chapter'
  current: string
  taken: string[]
}) {
  const { gameId } = useWorkspace()
  const actions = useGameActions(gameId)
  const [open, setOpen] = useState(false)
  const [value, setValue] = useState(current)
  const [busy, setBusy] = useState(false)
  const [serverError, setServerError] = useState<string | null>(null)
  useEffect(() => {
    if (open) {
      setValue(current)
      setServerError(null)
    }
  }, [open, current])
  const others = taken.filter((t) => t !== current)
  const error =
    value === current ? null : kind === 'variable' ? variableNameError(value, others) : slugError(value, others)

  async function submit() {
    if (error || value === current) return setOpen(false)
    setBusy(true)
    try {
      await actions.rename(kind, current, value)
      setOpen(false)
    } catch (e) {
      setServerError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        title="Rename everywhere"
        className="group inline-flex items-center gap-1 rounded px-1 font-mono text-sm text-zinc-200 hover:bg-surface-800"
      >
        {current}
        <Pencil className="size-3 text-zinc-600 group-hover:text-zinc-300" />
      </button>
      <Dialog
        open={open}
        onOpenChange={setOpen}
        title={`Rename ${kind}`}
        description="Every condition, effect and piece of text that uses it is updated too."
        footer={
          <>
            <Button onClick={() => setOpen(false)}>Cancel</Button>
            <Button variant="primary" loading={busy} disabled={!!error} onClick={() => void submit()}>
              Rename
            </Button>
          </>
        }
      >
        <form
          onSubmit={(e) => {
            e.preventDefault()
            void submit()
          }}
        >
          <Field error={error ?? serverError}>
            <Input autoFocus className="font-mono" value={value} onChange={(e) => setValue(e.target.value.toLowerCase())} />
          </Field>
        </form>
      </Dialog>
    </>
  )
}

export function ConfirmDelete({
  open,
  onOpenChange,
  title,
  description,
  onConfirm,
}: {
  open: boolean
  onOpenChange: (o: boolean) => void
  title: string
  description?: ReactNode
  onConfirm: () => void
}) {
  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title={title}
      description={description}
      footer={
        <>
          <Button onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button
            variant="danger"
            onClick={() => {
              onConfirm()
              onOpenChange(false)
            }}
          >
            Delete
          </Button>
        </>
      }
    />
  )
}
