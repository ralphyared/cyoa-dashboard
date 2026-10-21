import { useSortable } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import {
  ArrowRight,
  ChevronDown,
  ChevronRight,
  Copy,
  GripVertical,
  Lock,
  MoreHorizontal,
  Repeat1,
  Trash2,
  Zap,
} from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router'
import { ConditionField, EffectsField } from '@/components/editor/LogicFields'
import { ScenePicker } from '@/components/ScenePicker'
import {
  Badge,
  Button,
  Checkbox,
  Input,
  Menu,
  MenuContent,
  MenuItem,
  MenuTrigger,
  Segmented,
  Tip,
  cx,
  useReadOnly,
} from '@/components/ui'
import { useScenes } from '@/lib/queries'
import type { Choice, Issue } from '@/lib/types'
import { IssueList } from '@/components/IssueList'

export function newChoice(): Choice {
  const bytes = crypto.getRandomValues(new Uint8Array(4))
  const id = Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')
  return { id, text: '', target: '', condition: '', when_locked: 'hide', hint: '', effects: '', once: false }
}

export function ChoiceCard({
  gameId,
  index,
  choice,
  issues,
  focused,
  onChange,
  onDelete,
  onDuplicate,
  onCreateTarget,
  onHideIssue,
}: {
  gameId: string
  index: number
  choice: Choice
  issues: Issue[]
  focused: boolean
  onChange: (choice: Choice) => void
  onDelete: () => void
  onDuplicate: () => void
  onCreateTarget: (title: string) => Promise<string>
  onHideIssue: (issue: Issue) => void
}) {
  const [open, setOpen] = useState(focused)
  const ref = useRef<HTMLDivElement | null>(null)
  const textInput = useRef<HTMLInputElement>(null)
  const navigate = useNavigate()
  const scenes = useScenes(gameId)
  const target = scenes.find((s) => s.id === choice.target)
  const readOnly = useReadOnly()
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: choice.id,
    disabled: readOnly,
  })

  useEffect(() => {
    if (focused) {
      setOpen(true)
      ref.current?.scrollIntoView({ block: 'center', behavior: 'smooth' })
    }
  }, [focused])

  useEffect(() => {
    if (!choice.text && !choice.target && !readOnly) textInput.current?.focus()
    // focus brand-new choices once
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const set = (changes: Partial<Choice>) => onChange({ ...choice, ...changes })
  const hasErrors = issues.some((i) => i.severity === 'error')

  return (
    <div
      ref={(node) => {
        setNodeRef(node)
        ref.current = node
      }}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className={cx(
        'rounded-lg border bg-surface-900',
        hasErrors ? 'border-red-500/40' : 'border-surface-700',
        isDragging && 'z-10 opacity-80 shadow-xl',
      )}
    >
      {/* one row on wide screens; text above destination on phones */}
      <div className="flex flex-col gap-1.5 p-2 sm:flex-row sm:items-center">
        <div className="flex min-w-0 flex-1 items-center gap-1.5">
          {!readOnly && (
            <span
              {...attributes}
              {...listeners}
              className="cursor-grab touch-none text-zinc-600 hover:text-zinc-300"
              aria-label="Drag to reorder"
            >
              <GripVertical className="size-4" />
            </span>
          )}
          <span className="w-5 shrink-0 text-center font-mono text-xs text-zinc-500">{index + 1})</span>
          <Input
            ref={textInput}
            value={choice.text}
            onChange={(e) => set({ text: e.target.value })}
            placeholder="What the player can do…"
            className="min-w-0 flex-1"
          />
        </div>
        <div className="flex items-center gap-1.5 pl-[2.6rem] sm:pl-0">
        <ArrowRight className="size-3.5 shrink-0 text-zinc-600" />
        <ScenePicker
          gameId={gameId}
          className="min-w-0 flex-1 sm:w-56 sm:flex-none"
          value={choice.target}
          onChange={(t) => set({ target: t })}
          onCreate={onCreateTarget}
          placeholder="Leads to…"
        />
        <Tip content={target ? `Open “${target.title || target.id}”` : 'Choose a destination first'}>
          <Button
            size="sm"
            variant="ghost"
            disabled={!target}
            icon={<ArrowRight className="size-3.5" />}
            aria-label="Open destination scene"
            onClick={() => target && navigate(`/games/${gameId}/scenes/${target.pk}`)}
          />
        </Tip>
        {!readOnly && (
          <Menu>
            <MenuTrigger asChild>
              <Button size="sm" variant="ghost" icon={<MoreHorizontal className="size-4" />} aria-label="Choice actions" />
            </MenuTrigger>
            <MenuContent>
              <MenuItem icon={<Copy className="size-3.5" />} onSelect={onDuplicate}>
                Duplicate
              </MenuItem>
              <MenuItem danger icon={<Trash2 className="size-3.5" />} onSelect={onDelete}>
                Delete choice
              </MenuItem>
            </MenuContent>
          </Menu>
        )}
        </div>
      </div>

      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-2 border-t border-surface-800 px-3 py-1.5 text-left text-xs text-zinc-500 hover:text-zinc-300"
      >
        {open ? <ChevronDown className="size-3" /> : <ChevronRight className="size-3" />}
        {choice.condition.trim() ? (
          <Badge tone="accent" className="max-w-[45%] truncate font-mono">
            <Lock className="size-3 shrink-0" /> {choice.condition}
          </Badge>
        ) : (
          <span>Always available</span>
        )}
        {choice.effects.trim() && (
          <Badge className="max-w-[40%] truncate font-mono">
            <Zap className="size-3 shrink-0" /> {choice.effects.split('\n').filter(Boolean).join('; ')}
          </Badge>
        )}
        {choice.once && (
          <Badge>
            <Repeat1 className="size-3" /> once
          </Badge>
        )}
      </button>

      {open && (
        <div className="flex flex-col gap-4 border-t border-surface-800 px-3 py-3">
          <ConditionField
            gameId={gameId}
            label="Only available if…"
            value={choice.condition}
            onChange={(condition) => set({ condition })}
            footer={(result) =>
              choice.condition.trim() ? (
                <div className="flex flex-wrap items-center gap-2 rounded-md bg-surface-850 px-2 py-1.5">
                  <span className="text-xs text-zinc-400">When not available:</span>
                  <Segmented
                    size="xs"
                    disabled={readOnly}
                    value={choice.when_locked}
                    onChange={(when_locked) => set({ when_locked })}
                    options={[
                      { value: 'hide', label: 'hide it' },
                      { value: 'show', label: 'show it locked' },
                    ]}
                  />
                  {choice.when_locked === 'show' && (
                    <>
                      <Input
                        className="h-6 w-48 text-xs"
                        value={choice.hint}
                        onChange={(e) => set({ hint: e.target.value })}
                        placeholder={result?.hint ? `hint: ${result.hint}` : 'custom hint (optional)'}
                      />
                      <span className="font-mono text-xs text-zinc-500">
                        players see: -) {choice.text || '…'}{' '}
                        <span className="italic">[{choice.hint || result?.hint ? `Requires: ${choice.hint || result?.hint}` : 'Locked'}]</span>
                      </span>
                    </>
                  )}
                </div>
              ) : null
            }
          />
          <EffectsField gameId={gameId} label="When chosen…" value={choice.effects} onChange={(effects) => set({ effects })} />
          <Checkbox
            checked={choice.once}
            onChange={(once) => set({ once })}
            label="Can only be chosen once (disappears afterwards)"
          />
        </div>
      )}
      {issues.length > 0 && (
        <div className="px-3 pb-3">
          <IssueList issues={issues} onHide={readOnly ? undefined : onHideIssue} />
        </div>
      )}
    </div>
  )
}
