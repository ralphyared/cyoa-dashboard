import {
  closestCenter,
  DndContext,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core'
import { arrayMove, SortableContext, useSortable, verticalListSortingStrategy } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import {
  ChevronDown,
  ChevronRight,
  Flag,
  GripVertical,
  PanelLeftClose,
  PanelLeftOpen,
  Play,
  Plus,
  Search,
  Skull,
  Trophy,
} from 'lucide-react'
import { memo, useMemo, useState } from 'react'
import { NavLink, useNavigate, useParams } from 'react-router'
import { matchScene } from '@/components/ScenePicker'
import { Button, Checkbox, Tip, cx } from '@/components/ui'
import { useGame, useGameActions, useIssues } from '@/lib/queries'
import type { Chapter, GameDetail, Scene } from '@/lib/types'
import { issuesByScene, useWorkspace, type SceneIssueCounts } from './context'

interface SidebarScene {
  pk: number
  id: string
  title: string
  chapter: string | null
  ending: Scene['ending']
  text: string
}

interface SidebarData {
  scenes: SidebarScene[]
  chapters: Chapter[]
  start: string
}

function selectSidebar(game: GameDetail): SidebarData {
  return {
    scenes: game.scenes.map((s) => ({
      pk: s.pk,
      id: s.id,
      title: s.title,
      chapter: s.chapter,
      ending: s.ending,
      text: s.text,
    })),
    chapters: game.meta.chapters,
    start: game.meta.start_scene,
  }
}

export function Sidebar() {
  const { gameId } = useWorkspace()
  const { pk: currentPk } = useParams()
  const navigate = useNavigate()
  const data = useGame(gameId, selectSidebar).data
  const issues = useIssues(gameId).data
  const actions = useGameActions(gameId)
  const [query, setQuery] = useState('')
  const [problemsOnly, setProblemsOnly] = useState(false)
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({})
  const [hidden, setHidden] = useState(() => localStorage.getItem('cyoa.sidebarHidden') === '1')
  const counts = useMemo(() => issuesByScene(issues?.issues), [issues])
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }))

  const groups = useMemo(() => {
    if (!data) return []
    const q = query.trim().toLowerCase()
    const visible = data.scenes.filter((s) => {
      if (problemsOnly && !counts.has(s.id)) return false
      if (!q) return true
      return matchScene(s as Scene, q) || s.text.toLowerCase().includes(q)
    })
    const known = new Set(data.chapters.map((c) => c.id))
    const result: { key: string; chapter: Chapter | null; scenes: SidebarScene[] }[] = data.chapters.map(
      (chapter) => ({ key: chapter.id, chapter, scenes: visible.filter((s) => s.chapter === chapter.id) }),
    )
    const loose = visible.filter((s) => !s.chapter || !known.has(s.chapter))
    if (loose.length > 0 || data.chapters.length === 0) {
      result.push({ key: '', chapter: null, scenes: loose })
    }
    return result.filter((g) => g.scenes.length > 0 || (!q && !problemsOnly))
  }, [data, query, problemsOnly, counts])

  function toggleHidden() {
    setHidden((h) => {
      localStorage.setItem('cyoa.sidebarHidden', h ? '0' : '1')
      return !h
    })
  }

  async function newScene() {
    const current = data?.scenes.find((s) => String(s.pk) === currentPk)
    const scene = await actions.createScene({ title: 'New scene', chapter: current?.chapter ?? null })
    navigate(`/games/${gameId}/scenes/${scene.pk}?new=1`)
  }

  function onDragEnd(event: DragEndEvent, groupScenes: SidebarScene[]) {
    if (!data || !event.over || event.active.id === event.over.id) return
    const from = groupScenes.findIndex((s) => s.pk === event.active.id)
    const to = groupScenes.findIndex((s) => s.pk === event.over!.id)
    if (from < 0 || to < 0) return
    const reordered = arrayMove(groupScenes, from, to).map((s) => s.pk)
    // Keep every other scene where it was; slot this group's new order into its old positions.
    const groupSet = new Set(reordered)
    const queue = [...reordered]
    const order = data.scenes.map((s) => (groupSet.has(s.pk) ? queue.shift()! : s.pk))
    void actions.setOrder(order)
  }

  if (hidden) {
    return (
      <div className="flex w-10 shrink-0 flex-col items-center border-r border-surface-700 bg-surface-900 py-2">
        <Tip content="Show scenes">
          <Button variant="ghost" size="sm" icon={<PanelLeftOpen className="size-4" />} onClick={toggleHidden} />
        </Tip>
      </div>
    )
  }

  const searching = query.trim() !== '' || problemsOnly
  return (
    <aside className="flex w-64 shrink-0 flex-col border-r border-surface-700 bg-surface-900">
      <div className="flex items-center gap-1 px-3 pt-3 pb-2">
        <div className="text-xs font-semibold tracking-wide text-zinc-400 uppercase">
          Scenes <span className="text-zinc-600">{data?.scenes.length ?? 0}</span>
        </div>
        <div className="ml-auto flex gap-0.5">
          <Button size="xs" variant="ghost" icon={<Plus className="size-3.5" />} onClick={() => void newScene()}>
            New
          </Button>
          <Tip content="Hide">
            <Button size="xs" variant="ghost" icon={<PanelLeftClose className="size-3.5" />} onClick={toggleHidden} />
          </Tip>
        </div>
      </div>
      <div className="px-3 pb-2">
        <div className="relative">
          <Search className="pointer-events-none absolute top-1/2 left-2 size-3.5 -translate-y-1/2 text-zinc-500" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search titles, ids, text…"
            className="h-7 w-full rounded-md border border-surface-700 bg-surface-950 pr-2 pl-7 text-xs text-zinc-200 outline-none placeholder:text-zinc-600 focus:border-accent-600"
          />
        </div>
        <Checkbox className="mt-2 text-xs" checked={problemsOnly} onChange={setProblemsOnly} label="Only scenes with problems" />
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-1.5 pb-4">
        {groups.map((group) => {
          const isCollapsed = collapsed[group.key] && !searching
          return (
            <div key={group.key || '__none'} className="mb-1">
              {(data?.chapters.length ?? 0) > 0 && (
                <button
                  type="button"
                  onClick={() => setCollapsed((c) => ({ ...c, [group.key]: !c[group.key] }))}
                  className="flex w-full items-center gap-1.5 rounded px-1.5 py-1 text-left text-xs font-medium text-zinc-400 hover:text-zinc-200"
                >
                  {isCollapsed ? <ChevronRight className="size-3" /> : <ChevronDown className="size-3" />}
                  <span className="size-2 shrink-0 rounded-full" style={{ background: group.chapter?.color || '#52525b' }} />
                  <span className="truncate">{group.chapter ? group.chapter.title || group.chapter.id : 'No chapter'}</span>
                  <span className="ml-auto text-zinc-600">{group.scenes.length}</span>
                </button>
              )}
              {!isCollapsed && (
                <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={(e) => onDragEnd(e, group.scenes)}>
                  <SortableContext items={group.scenes.map((s) => s.pk)} strategy={verticalListSortingStrategy}>
                    {group.scenes.map((scene) => (
                      <SceneRow
                        key={scene.pk}
                        scene={scene}
                        gameId={gameId}
                        isStart={scene.id === data?.start}
                        counts={counts.get(scene.id)}
                        draggable={!searching}
                      />
                    ))}
                  </SortableContext>
                </DndContext>
              )}
            </div>
          )
        })}
      </div>
    </aside>
  )
}

const SceneRow = memo(function SceneRow({
  scene,
  gameId,
  isStart,
  counts,
  draggable,
}: {
  scene: SidebarScene
  gameId: string
  isStart: boolean
  counts?: SceneIssueCounts
  draggable: boolean
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: scene.pk,
    disabled: !draggable,
  })
  const EndingIcon =
    scene.ending?.kind === 'death' ? Skull : scene.ending?.kind === 'victory' ? Trophy : scene.ending ? Flag : null
  return (
    <div
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className={cx('group relative', isDragging && 'z-10 opacity-70')}
    >
      <NavLink
        to={`/games/${gameId}/scenes/${scene.pk}`}
        className={({ isActive }) =>
          cx(
            'flex items-center gap-1.5 rounded py-1 pr-2 pl-5 text-sm',
            isActive ? 'bg-surface-700 text-zinc-100' : 'text-zinc-300 hover:bg-surface-800',
          )
        }
      >
        {isStart && <Play className="size-3 shrink-0 fill-accent-400 text-accent-400" aria-label="Start scene" />}
        <span className={cx('min-w-0 flex-1 truncate', !scene.title && 'font-mono text-xs text-zinc-400')}>
          {scene.title || scene.id}
        </span>
        {EndingIcon && (
          <EndingIcon
            className={cx(
              'size-3 shrink-0',
              scene.ending?.kind === 'death' ? 'text-red-400' : scene.ending?.kind === 'victory' ? 'text-amber-300' : 'text-zinc-400',
            )}
          />
        )}
        {counts && (
          <span
            title={`${counts.errors} errors, ${counts.warnings} warnings`}
            className={cx('size-1.5 shrink-0 rounded-full', counts.errors ? 'bg-red-400' : 'bg-amber-400')}
          />
        )}
      </NavLink>
      {draggable && (
        <span
          {...attributes}
          {...listeners}
          className="absolute top-1/2 left-0.5 -translate-y-1/2 cursor-grab text-zinc-600 opacity-0 group-hover:opacity-100"
          aria-label="Drag to reorder"
        >
          <GripVertical className="size-3.5" />
        </span>
      )}
    </div>
  )
})
