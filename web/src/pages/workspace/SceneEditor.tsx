import {
  closestCenter,
  DndContext,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core'
import { arrayMove, SortableContext, sortableKeyboardCoordinates, verticalListSortingStrategy } from '@dnd-kit/sortable'
import type { EditorView } from '@codemirror/view'
import {
  AlertTriangle,
  ArrowRight,
  Bold,
  Braces,
  ChevronDown,
  ChevronRight,
  History,
  Italic,
  MoreHorizontal,
  Palette,
  Pencil,
  Play,
  Plus,
  ScissorsLineDashed,
  Star,
  Trash2,
  Variable as VariableIcon,
} from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router'
import { CodeEditor } from '@/components/editor/CodeEditor'
import { EffectsField } from '@/components/editor/LogicFields'
import {
  Badge,
  Button,
  Dialog,
  Empty,
  Field,
  Input,
  Menu,
  MenuContent,
  MenuItem,
  MenuTrigger,
  Select,
  Textarea,
  Tip,
  cx,
} from '@/components/ui'
import { slugError } from '@/lib/format'
import { useGame, useGameActions, useIssues, useMeta, useSaver, useSaveState, useScene } from '@/lib/queries'
import type { Choice, EndingKind, GameDetail, Scene } from '@/lib/types'
import { IssueList } from '@/components/IssueList'
import { ChoiceCard, newChoice } from './ChoiceCard'
import { useWorkspace } from './context'
import { HistoryDialog } from './HistoryDialog'

export function SceneEditorPage() {
  const { pk: pkParam } = useParams()
  const { gameId } = useWorkspace()
  const pk = Number(pkParam)
  const scene = useScene(gameId, Number.isFinite(pk) ? pk : null)
  if (!scene) {
    return (
      <Empty title="Scene not found">
        It may have been deleted. Pick another scene from the sidebar.
      </Empty>
    )
  }
  return <SceneEditor key={scene.pk} scene={scene} />
}

const COLORS = ['red', 'green', 'yellow', 'blue', 'magenta', 'cyan', 'gray', 'orange', 'purple', 'gold', 'pink']

function wordCount(text: string): number {
  const stripped = text.replace(/\{[^}]*\}/g, ' ').replace(/\[\/?[A-Za-z_#0-9]*\]/g, ' ')
  return (stripped.match(/[A-Za-z0-9’']+/g) ?? []).length
}

interface Incoming {
  pk: number
  title: string
  id: string
  label: string
}

export function SceneEditor({ scene, compact }: { scene: Scene; compact?: boolean }) {
  const { gameId, playtest } = useWorkspace()
  const actions = useGameActions(gameId)
  const meta = useMeta(gameId)
  const saver = useSaver()
  const saveState = useSaveState(`scene:${scene.pk}`)
  const issues = useIssues(gameId).data?.issues
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const textView = useRef<EditorView | null>(null)
  const titleInput = useRef<HTMLInputElement>(null)
  const [renaming, setRenaming] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [showArt, setShowArt] = useState(scene.art.trim() !== '')
  const [showArrival, setShowArrival] = useState(scene.on_enter.trim() !== '')
  const focusChoice = params.get('choice')

  const update = useCallback(
    (changes: Partial<Scene>) => actions.updateScene(scene.pk, changes),
    [actions, scene.pk],
  )

  useEffect(() => {
    if (params.get('new') === '1' && titleInput.current) {
      titleInput.current.focus()
      titleInput.current.select()
      params.delete('new')
      setParams(params, { replace: true })
    }
  }, [params, setParams])

  const incomingSelector = useCallback(
    (game: GameDetail): Incoming[] => {
      const result: Incoming[] = []
      for (const s of game.scenes) {
        for (const c of s.choices) {
          if (c.target === scene.id) result.push({ pk: s.pk, title: s.title, id: s.id, label: c.text })
        }
      }
      return result
    },
    [scene.id],
  )
  const incoming = useGame(gameId, incomingSelector).data ?? []
  const rulesHere = (meta?.rules ?? []).filter((r) => r.goto === scene.id)
  const isStart = meta?.start_scene === scene.id

  const sceneIssues = (issues ?? []).filter((i) => i.scene === scene.id)
  const generalIssues = sceneIssues.filter((i) => !i.choice)
  const choiceIssues = (choiceId: string) => sceneIssues.filter((i) => i.choice === choiceId)

  const setChoices = (choices: Choice[]) => update({ choices })
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  )
  function onDragEnd(event: DragEndEvent) {
    if (!event.over || event.active.id === event.over.id) return
    const from = scene.choices.findIndex((c) => c.id === event.active.id)
    const to = scene.choices.findIndex((c) => c.id === event.over!.id)
    if (from >= 0 && to >= 0) setChoices(arrayMove(scene.choices, from, to))
  }

  async function createTarget(title: string): Promise<string> {
    const created = await actions.createScene({ title, chapter: scene.chapter })
    return created.id
  }

  async function remove() {
    await actions.deleteScene(scene.pk)
    setDeleting(false)
    navigate(`/games/${gameId}`)
  }

  // -- text toolbar ----------------------------------------------------------------------
  function wrap(before: string, after: string, placeholder = '') {
    const view = textView.current
    if (!view) return
    const { from, to } = view.state.selection.main
    const selected = view.state.sliceDoc(from, to) || placeholder
    view.dispatch({
      changes: { from, to, insert: before + selected + after },
      selection: { anchor: from + before.length, head: from + before.length + selected.length },
    })
    view.focus()
  }
  function insert(text: string, cursorOffset = text.length) {
    const view = textView.current
    if (!view) return
    const { from, to } = view.state.selection.main
    view.dispatch({ changes: { from, to, insert: text }, selection: { anchor: from + cursorOffset } })
    view.focus()
  }

  const words = useMemo(() => wordCount(scene.text), [scene.text])

  return (
    <div className="h-full overflow-y-auto">
      <div className={cx('mx-auto flex flex-col gap-5 px-4 py-4 sm:px-6 sm:py-5', compact ? 'max-w-none' : 'max-w-3xl')}>
        {/* header */}
        <div className="flex flex-col gap-2">
          <div className="flex items-start gap-2">
            <input
              ref={titleInput}
              value={scene.title}
              onChange={(e) => update({ title: e.target.value })}
              placeholder="Scene title (for you; players see the chapter)"
              className="min-w-0 flex-1 rounded-md border border-transparent bg-transparent px-1 py-0.5 text-lg font-semibold sm:text-xl text-zinc-100 outline-none placeholder:font-normal placeholder:text-zinc-600 hover:border-surface-700 focus:border-accent-600"
            />
            <Button
              size="sm"
              variant="primary"
              icon={<Play className="size-3.5" />}
              onClick={() => playtest(scene.id)}
              aria-label="Play from here"
            >
              <span className="hidden sm:inline">Play from here</span>
            </Button>
            <Menu>
              <MenuTrigger asChild>
                <Button size="sm" variant="ghost" icon={<MoreHorizontal className="size-4" />} aria-label="Scene actions" />
              </MenuTrigger>
              <MenuContent>
                <MenuItem icon={<Pencil className="size-3.5" />} onSelect={() => setRenaming(true)}>
                  Change id…
                </MenuItem>
                <MenuItem
                  icon={<Star className="size-3.5" />}
                  disabled={isStart}
                  onSelect={() => actions.updateMeta({ start_scene: scene.id })}
                >
                  Make this the start scene
                </MenuItem>
                <MenuItem icon={<History className="size-3.5" />} onSelect={() => setHistoryOpen(true)}>
                  History…
                </MenuItem>
                <MenuItem danger icon={<Trash2 className="size-3.5" />} onSelect={() => setDeleting(true)}>
                  Delete scene…
                </MenuItem>
              </MenuContent>
            </Menu>
          </div>
          <div className="flex flex-wrap items-center gap-2 px-1">
            <Tip content="The scene's id, used in choices and visited(). Click to change it everywhere.">
              <button
                type="button"
                onClick={() => setRenaming(true)}
                className="rounded bg-surface-800 px-1.5 py-0.5 font-mono text-xs text-zinc-400 hover:text-zinc-100"
              >
                {scene.id}
              </button>
            </Tip>
            {isStart && <Badge tone="accent">start scene</Badge>}
            <Select
              className="h-7 w-auto max-w-48 text-xs"
              value={scene.chapter ?? ''}
              onChange={(e) => update({ chapter: e.target.value || null })}
            >
              <option value="">No chapter</option>
              {meta?.chapters.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.title || c.id}
                </option>
              ))}
              {scene.chapter && !meta?.chapters.some((c) => c.id === scene.chapter) && (
                <option value={scene.chapter}>{scene.chapter} (missing)</option>
              )}
            </Select>
            <Select
              className={cx('h-7 w-auto text-xs', scene.ending && 'border-amber-500/50')}
              value={scene.ending?.kind ?? ''}
              onChange={(e) =>
                update({
                  ending: e.target.value
                    ? { kind: e.target.value as EndingKind, title: scene.ending?.title ?? '' }
                    : null,
                })
              }
            >
              <option value="">Not an ending</option>
              <option value="death">Ending: death</option>
              <option value="victory">Ending: victory</option>
              <option value="neutral">Ending: other</option>
            </Select>
            {scene.ending && (
              <Input
                className="h-7 w-full text-xs sm:w-56"
                placeholder="Ending name (shown on the end screen)"
                value={scene.ending.title}
                onChange={(e) => update({ ending: { ...scene.ending!, title: e.target.value } })}
              />
            )}
          </div>
        </div>

        {saveState.status === 'conflict' && (
          <div className="flex items-center gap-3 rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm text-amber-200">
            <AlertTriangle className="size-4 shrink-0" />
            <div className="flex-1">This scene was changed somewhere else (another tab?).</div>
            <Button size="sm" onClick={() => saver.useTheirs(`scene:${scene.pk}`)}>
              Load theirs
            </Button>
            <Button size="sm" variant="primary" onClick={() => saver.keepMine(`scene:${scene.pk}`)}>
              Keep mine
            </Button>
          </div>
        )}
        {saveState.status === 'error' && (
          <div className="rounded-md border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-300">
            Couldn't save: {saveState.message}
          </div>
        )}

        {generalIssues.length > 0 && <IssueList issues={generalIssues} />}

        {/* text */}
        <section className="flex flex-col gap-1.5">
          <div className="flex items-center gap-1">
            <ToolbarButton label="Bold" onClick={() => wrap('**', '**', 'bold text')}>
              <Bold className="size-3.5" />
            </ToolbarButton>
            <ToolbarButton label="Italic" onClick={() => wrap('*', '*', 'italic text')}>
              <Italic className="size-3.5" />
            </ToolbarButton>
            <Menu>
              <Tip content="Color">
                <MenuTrigger asChild>
                  <Button size="xs" variant="ghost" icon={<Palette className="size-3.5" />} />
                </MenuTrigger>
              </Tip>
              <MenuContent align="start">
                {COLORS.map((c) => (
                  <MenuItem key={c} onSelect={() => wrap(`[${c}]`, `[/${c}]`, 'colored text')}>
                    <span className="size-2.5 rounded-full" style={{ background: c === 'gray' ? '#71717a' : c }} />
                    {c}
                  </MenuItem>
                ))}
              </MenuContent>
            </Menu>
            <Menu>
              <Tip content="Insert a variable's value">
                <MenuTrigger asChild>
                  <Button size="xs" variant="ghost" icon={<VariableIcon className="size-3.5" />} />
                </MenuTrigger>
              </Tip>
              <MenuContent align="start">
                {meta?.variables.length === 0 && (
                  <MenuItem disabled onSelect={() => undefined}>
                    No variables yet
                  </MenuItem>
                )}
                {meta?.variables.map((v) => (
                  <MenuItem key={v.name} onSelect={() => insert(`{${v.name}}`)}>
                    {v.label || v.name} <span className="font-mono text-xs text-zinc-500">{v.name}</span>
                  </MenuItem>
                ))}
              </MenuContent>
            </Menu>
            <ToolbarButton label="Conditional text: only shown when a condition is true" onClick={() => wrap('{if }', '{/if}', 'text')}>
              <Braces className="size-3.5" />
            </ToolbarButton>
            <ToolbarButton label="Page break (player presses Enter to continue)" onClick={() => insert('\n---\n')}>
              <ScissorsLineDashed className="size-3.5" />
            </ToolbarButton>
            <span className="ml-auto text-xs text-zinc-500">{words.toLocaleString()} words</span>
          </div>
          <CodeEditor
            gameId={gameId}
            mode="markup"
            prose
            value={scene.text}
            onChange={(text) => update({ text })}
            placeholder="What happens here? Use {gold} to show a value, {if has(&quot;rope&quot;)}…{/if} for text that only sometimes appears."
            minHeight="10rem"
            editorRef={(v) => (textView.current = v)}
          />
        </section>

        {/* art & arrival */}
        <Collapsible open={showArt} onToggle={() => setShowArt((s) => !s)} title="ASCII art" summary={scene.art.trim() ? `${scene.art.split('\n').length} lines` : 'none'}>
          <Textarea
            value={scene.art}
            onChange={(e) => update({ art: e.target.value })}
            rows={Math.min(16, Math.max(4, scene.art.split('\n').length + 1))}
            spellCheck={false}
            placeholder="Shown above the text, centered. Paste ASCII art here."
            className="font-mono text-xs leading-tight whitespace-pre"
            wrap="off"
          />
        </Collapsible>
        <Collapsible
          open={showArrival}
          onToggle={() => setShowArrival((s) => !s)}
          title="When the player arrives"
          summary={scene.on_enter.trim() ? scene.on_enter.split('\n').filter(Boolean).join('; ') : 'nothing changes'}
        >
          <EffectsField gameId={gameId} label="Effects applied every time this scene is entered" value={scene.on_enter} onChange={(on_enter) => update({ on_enter })} />
        </Collapsible>

        {/* choices */}
        <section className="flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-semibold tracking-wide text-zinc-400 uppercase">
              Choices {scene.ending && <span className="font-normal normal-case text-amber-400">— hidden: this is an ending</span>}
            </h3>
          </div>
          <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
            <SortableContext items={scene.choices.map((c) => c.id)} strategy={verticalListSortingStrategy}>
              <div className="flex flex-col gap-2">
                {scene.choices.map((choice, i) => (
                  <ChoiceCard
                    key={choice.id}
                    gameId={gameId}
                    index={i}
                    choice={choice}
                    issues={choiceIssues(choice.id)}
                    focused={focusChoice === choice.id}
                    onChange={(c) => setChoices(scene.choices.map((x) => (x.id === choice.id ? c : x)))}
                    onDelete={() => setChoices(scene.choices.filter((x) => x.id !== choice.id))}
                    onDuplicate={() => {
                      const copy = { ...choice, id: newChoice().id }
                      const next = [...scene.choices]
                      next.splice(i + 1, 0, copy)
                      setChoices(next)
                    }}
                    onCreateTarget={createTarget}
                  />
                ))}
              </div>
            </SortableContext>
          </DndContext>
          {!scene.ending && scene.choices.length === 0 && (
            <div className="rounded-md border border-dashed border-surface-600 px-3 py-4 text-center text-sm text-zinc-500">
              No choices yet. Add one, or mark this scene as an ending.
            </div>
          )}
          <div>
            <Button size="sm" icon={<Plus className="size-3.5" />} onClick={() => setChoices([...scene.choices, newChoice()])}>
              Add choice
            </Button>
          </div>
        </section>

        {/* incoming */}
        <section className="flex flex-col gap-1.5">
          <h3 className="text-xs font-semibold tracking-wide text-zinc-400 uppercase">What leads here</h3>
          {incoming.length === 0 && rulesHere.length === 0 && !isStart && (
            <div className="text-sm text-zinc-500">Nothing yet: no choice leads to this scene.</div>
          )}
          <div className="flex flex-col gap-0.5">
            {isStart && <div className="text-sm text-zinc-400">▶ The game starts here.</div>}
            {incoming.map((link, i) => (
              <Link
                key={`${link.pk}-${i}`}
                to={`/games/${gameId}/scenes/${link.pk}`}
                className="flex items-center gap-2 rounded px-1.5 py-1 text-sm hover:bg-surface-800"
              >
                <span className="text-zinc-300">{link.title || link.id}</span>
                <ArrowRight className="size-3 text-zinc-600" />
                <span className="truncate text-zinc-500 italic">“{link.label || 'untitled choice'}”</span>
              </Link>
            ))}
            {rulesHere.map((rule) => (
              <Link key={rule.id} to={`/games/${gameId}/rules`} className="rounded px-1.5 py-1 text-sm text-zinc-400 hover:bg-surface-800">
                Rule “{rule.name || rule.condition}” sends the player here
              </Link>
            ))}
          </div>
        </section>

        {/* notes */}
        <Field label="Notes (private, never shown to players)">
          <Textarea
            value={scene.notes}
            onChange={(e) => update({ notes: e.target.value })}
            rows={Math.max(2, scene.notes.split('\n').length)}
            placeholder="Ideas, todos, continuity reminders…"
          />
        </Field>
        <Field label="Tags" hint="Comma separated. Find them with #tag in the sidebar search.">
          <Input
            value={scene.tags.join(', ')}
            onChange={(e) =>
              update({ tags: e.target.value.split(',').map((t) => t.trim()).filter(Boolean) })
            }
            placeholder="e.g. draft, combat"
          />
        </Field>
      </div>

      <RenameSceneDialog open={renaming} onOpenChange={setRenaming} scene={scene} />
      <HistoryDialog open={historyOpen} onOpenChange={setHistoryOpen} scene={scene} />
      <Dialog
        open={deleting}
        onOpenChange={setDeleting}
        title={`Delete “${scene.title || scene.id}”?`}
        description={
          incoming.length > 0
            ? `${incoming.length} choice${incoming.length === 1 ? '' : 's'} lead here and will become broken links. You can restore the scene from the trash.`
            : 'You can restore it from the trash.'
        }
        footer={
          <>
            <Button onClick={() => setDeleting(false)}>Cancel</Button>
            <Button variant="danger" onClick={() => void remove()}>
              Delete
            </Button>
          </>
        }
      />
    </div>
  )
}

function ToolbarButton({ label, onClick, children }: { label: string; onClick: () => void; children: ReactNode }) {
  return (
    <Tip content={label}>
      <Button size="xs" variant="ghost" onClick={onClick} aria-label={label}>
        {children}
      </Button>
    </Tip>
  )
}

function Collapsible({
  open,
  onToggle,
  title,
  summary,
  children,
}: {
  open: boolean
  onToggle: () => void
  title: string
  summary: string
  children: ReactNode
}) {
  return (
    <section className="flex flex-col gap-2">
      <button type="button" onClick={onToggle} className="flex items-center gap-1.5 text-left">
        {open ? <ChevronDown className="size-3.5 text-zinc-500" /> : <ChevronRight className="size-3.5 text-zinc-500" />}
        <span className="text-xs font-semibold tracking-wide text-zinc-400 uppercase">{title}</span>
        {!open && <span className="truncate text-xs text-zinc-600">{summary}</span>}
      </button>
      {open && children}
    </section>
  )
}

function RenameSceneDialog({
  open,
  onOpenChange,
  scene,
}: {
  open: boolean
  onOpenChange: (o: boolean) => void
  scene: Scene
}) {
  const { gameId } = useWorkspace()
  const actions = useGameActions(gameId)
  const taken = useGame(gameId, (g) => g.scenes.map((s) => s.id)).data ?? []
  const [value, setValue] = useState(scene.id)
  const [busy, setBusy] = useState(false)
  const [serverError, setServerError] = useState<string | null>(null)
  useEffect(() => {
    if (open) {
      setValue(scene.id)
      setServerError(null)
    }
  }, [open, scene.id])
  const error = value === scene.id ? null : slugError(value, taken.filter((t) => t !== scene.id))

  async function submit() {
    if (error || value === scene.id) return onOpenChange(false)
    setBusy(true)
    try {
      await actions.renameScene(scene.pk, value)
      onOpenChange(false)
    } catch (e) {
      setServerError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title="Change scene id"
      description="Every choice, rule and visited() check that uses this scene is updated too."
      footer={
        <>
          <Button onClick={() => onOpenChange(false)}>Cancel</Button>
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
  )
}
