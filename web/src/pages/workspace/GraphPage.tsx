import dagre from '@dagrejs/dagre'
import {
  Background,
  Controls,
  Handle,
  MarkerType,
  MiniMap,
  Position,
  ReactFlow,
  ReactFlowProvider,
  useNodesState,
  useReactFlow,
  type Connection,
  type Edge,
  type Node,
  type NodeProps,
  type OnConnectEnd,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { Flag, LayoutGrid, Play, Repeat, Search, Skull, Tag, Trophy, X } from 'lucide-react'
import { memo, useCallback, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router'
import { matchScene } from '@/components/ScenePicker'
import { Button, Checkbox, Dialog, Segmented, Select, cx } from '@/components/ui'
import { useIsPhone } from '@/lib/media'
import { useGame, useGameActions, useIssues, useScene } from '@/lib/queries'
import type { Chapter, GameDetail, Scene } from '@/lib/types'
import { newChoice } from './ChoiceCard'
import { issuesByScene, useWorkspace, type SceneIssueCounts } from './context'
import { SceneEditor } from './SceneEditor'

const NODE_W = 220
const NODE_H = 86
type Direction = 'TB' | 'LR'

interface SceneNodeData extends Record<string, unknown> {
  scene: Scene
  isStart: boolean
  issues?: SceneIssueCounts
  chapter?: Chapter
  dimmed: boolean
  direction: Direction
  loops: number
}

type SceneNode = Node<SceneNodeData, 'scene'>

function layout(scenes: Scene[], direction: Direction): Map<number, { x: number; y: number }> {
  const g = new dagre.graphlib.Graph()
  g.setGraph({ rankdir: direction, nodesep: 40, ranksep: 70, marginx: 20, marginy: 20 })
  g.setDefaultEdgeLabel(() => ({}))
  const byId = new Map(scenes.map((s) => [s.id, s]))
  for (const s of scenes) g.setNode(String(s.pk), { width: NODE_W, height: NODE_H })
  for (const s of scenes) {
    for (const c of s.choices) {
      const target = byId.get(c.target)
      if (target && target.pk !== s.pk) g.setEdge(String(s.pk), String(target.pk))
    }
  }
  dagre.layout(g)
  const result = new Map<number, { x: number; y: number }>()
  for (const s of scenes) {
    const n = g.node(String(s.pk))
    if (n) result.set(s.pk, { x: n.x - NODE_W / 2, y: n.y - NODE_H / 2 })
  }
  return result
}

const SceneNodeView = memo(function SceneNodeView({ data, selected }: NodeProps<SceneNode>) {
  const { scene, isStart, issues, chapter, dimmed, direction, loops } = data
  const EndingIcon =
    scene.ending?.kind === 'death' ? Skull : scene.ending?.kind === 'victory' ? Trophy : scene.ending ? Flag : null
  const preview = scene.text.replace(/\{[^}]*\}|\*\*|\*|\[\/?[a-z_#0-9]*\]/gi, '').slice(0, 90)
  return (
    <div
      className={cx(
        'relative overflow-hidden rounded-md border bg-surface-850 text-left shadow-md transition-opacity',
        selected ? 'border-accent-400 ring-1 ring-accent-400' : issues?.errors ? 'border-red-500/60' : 'border-surface-600',
        scene.ending && !selected && 'border-dashed',
        dimmed && 'opacity-25',
      )}
      style={{ width: NODE_W, height: NODE_H }}
    >
      <Handle type="target" position={direction === 'TB' ? Position.Top : Position.Left} className="!size-2 !border-surface-950 !bg-zinc-500" />
      <div className="h-1" style={{ background: chapter?.color || '#3f3f46' }} />
      <div className="flex flex-col gap-0.5 px-2.5 py-1.5">
        <div className="flex items-center gap-1.5">
          {isStart && <Play className="size-3 shrink-0 fill-accent-400 text-accent-400" />}
          <span className="min-w-0 flex-1 truncate text-sm font-medium text-zinc-100">{scene.title || scene.id}</span>
          {EndingIcon && (
            <EndingIcon className={cx('size-3.5 shrink-0', scene.ending?.kind === 'death' ? 'text-red-400' : scene.ending?.kind === 'victory' ? 'text-amber-300' : 'text-zinc-400')} />
          )}
          {issues && <span className={cx('size-2 shrink-0 rounded-full', issues.errors ? 'bg-red-400' : 'bg-amber-400')} />}
        </div>
        <div className="line-clamp-2 text-[11px] leading-snug text-zinc-500">{preview || <i>no text yet</i>}</div>
        <div className="mt-auto flex items-center gap-2 font-mono text-[10px] text-zinc-600">
          <span className="truncate">{scene.id}</span>
          {loops > 0 && (
            <span className="flex items-center gap-0.5" title="Choices that lead back to this scene">
              <Repeat className="size-2.5" /> {loops}
            </span>
          )}
        </div>
      </div>
      <Handle type="source" position={direction === 'TB' ? Position.Bottom : Position.Right} className="!size-2.5 !border-surface-950 !bg-accent-500" />
    </div>
  )
})

const nodeTypes = { scene: SceneNodeView }

export function GraphPage() {
  return (
    <ReactFlowProvider>
      <Graph />
    </ReactFlowProvider>
  )
}

function selectGraph(game: GameDetail) {
  return { scenes: game.scenes, chapters: game.meta.chapters, start: game.meta.start_scene }
}

function Graph() {
  const { gameId } = useWorkspace()
  const data = useGame(gameId, selectGraph).data
  const issues = useIssues(gameId).data
  const actions = useGameActions(gameId)
  const flow = useReactFlow()
  const [params, setParams] = useSearchParams()
  const selectedPk = params.get('scene') ? Number(params.get('scene')) : null
  const selectedScene = useScene(gameId, selectedPk)
  const [direction, setDirection] = useState<Direction>(() => (localStorage.getItem('cyoa.graphDir') as Direction) || 'TB')
  const [labels, setLabels] = useState(() => localStorage.getItem('cyoa.graphLabels') !== '0')
  const [chapterFilter, setChapterFilter] = useState('')
  const [search, setSearch] = useState('')
  const [confirmLayout, setConfirmLayout] = useState(false)
  const counts = useMemo(() => issuesByScene(issues?.issues), [issues])
  const isPhone = useIsPhone()

  const scenes = data?.scenes
  const fallback = useMemo(() => (scenes ? layout(scenes, direction) : new Map()), [
    // recompute only when the graph's shape changes, not on text edits
    // eslint-disable-next-line react-hooks/exhaustive-deps
    scenes && JSON.stringify(scenes.map((s) => [s.pk, s.id, s.choices.map((c) => c.target)])),
    direction,
  ])

  const builtNodes = useMemo((): SceneNode[] => {
    if (!data) return []
    const chapters = new Map(data.chapters.map((c) => [c.id, c]))
    return data.scenes.map((scene) => {
      const pos = scene.position ? { x: scene.position[0], y: scene.position[1] } : fallback.get(scene.pk) ?? { x: 0, y: 0 }
      return {
        id: String(scene.pk),
        type: 'scene',
        position: pos,
        selected: scene.pk === selectedPk,
        data: {
          scene,
          isStart: scene.id === data.start,
          issues: counts.get(scene.id),
          chapter: scene.chapter ? chapters.get(scene.chapter) : undefined,
          dimmed: chapterFilter !== '' && (scene.chapter ?? '__none') !== chapterFilter,
          direction,
          loops: scene.choices.filter((c) => c.target === scene.id).length,
        },
      }
    })
  }, [data, fallback, counts, chapterFilter, direction, selectedPk])

  const [nodes, setNodes, onNodesChange] = useNodesState<SceneNode>(builtNodes)
  useEffect(() => setNodes(builtNodes), [builtNodes, setNodes])

  const edges = useMemo((): Edge[] => {
    if (!data) return []
    const byId = new Map(data.scenes.map((s) => [s.id, s]))
    const result: Edge[] = []
    for (const s of data.scenes) {
      for (const c of s.choices) {
        const target = byId.get(c.target)
        if (!target || target.pk === s.pk) continue
        const conditional = c.condition.trim() !== ''
        const text = c.text.length > 28 ? `${c.text.slice(0, 27)}…` : c.text
        result.push({
          id: `${s.pk}-${c.id}`,
          source: String(s.pk),
          target: String(target.pk),
          label: labels ? text : undefined,
          labelBgPadding: [4, 2],
          style: conditional ? { strokeDasharray: '5 4' } : undefined,
          markerEnd: { type: MarkerType.ArrowClosed, width: 14, height: 14 },
          animated: false,
        })
      }
    }
    return result
  }, [data, labels])

  const select = useCallback(
    (pk: number | null) => {
      if (pk === null) params.delete('scene')
      else params.set('scene', String(pk))
      setParams(params, { replace: true })
    },
    [params, setParams],
  )

  const onConnect = useCallback(
    (connection: Connection) => {
      const source = data?.scenes.find((s) => String(s.pk) === connection.source)
      const target = data?.scenes.find((s) => String(s.pk) === connection.target)
      if (!source || !target) return
      actions.updateScene(source.pk, { choices: [...source.choices, { ...newChoice(), target: target.id }] })
    },
    [data, actions],
  )

  const onConnectEnd: OnConnectEnd = useCallback(
    (event, state) => {
      if (state.isValid || !state.fromNode || !data) return
      const source = data.scenes.find((s) => String(s.pk) === state.fromNode!.id)
      if (!source) return
      const point = 'changedTouches' in event ? event.changedTouches[0] : event
      const position = flow.screenToFlowPosition({ x: point.clientX, y: point.clientY })
      void (async () => {
        const created = await actions.createScene({
          title: 'New scene',
          chapter: source.chapter,
          position: [position.x - NODE_W / 2, position.y],
        })
        actions.updateScene(source.pk, { choices: [...source.choices, { ...newChoice(), target: created.id }] })
        select(created.pk)
      })()
    },
    [data, actions, flow, select],
  )

  function autoLayout() {
    if (!data) return
    const positions = layout(data.scenes, direction)
    const payload: Record<number, [number, number]> = {}
    for (const [pk, p] of positions) payload[pk] = [Math.round(p.x), Math.round(p.y)]
    void actions.setPositions(payload).then(() => requestAnimationFrame(() => flow.fitView({ duration: 300 })))
    setConfirmLayout(false)
  }

  function jumpTo(query: string) {
    const scene = data?.scenes.find((s) => matchScene(s, query))
    if (!scene) return
    const node = flow.getNode(String(scene.pk))
    if (node) flow.setCenter(node.position.x + NODE_W / 2, node.position.y + NODE_H / 2, { zoom: 1.1, duration: 400 })
    select(scene.pk)
  }

  if (!data) return null
  return (
    <div className="flex h-full">
      <div className="relative min-w-0 flex-1">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          onNodesChange={onNodesChange}
          onNodeClick={(_, node) => select(Number(node.id))}
          onPaneClick={() => select(null)}
          onNodeDragStop={(_, _node, dragged) => {
            const payload: Record<number, [number, number]> = {}
            for (const n of dragged) payload[Number(n.id)] = [Math.round(n.position.x), Math.round(n.position.y)]
            void actions.setPositions(payload)
          }}
          onConnect={onConnect}
          onConnectEnd={onConnectEnd}
          fitView
          fitViewOptions={{ maxZoom: 1 }}
          minZoom={0.1}
          maxZoom={2}
          deleteKeyCode={null}
          proOptions={{ hideAttribution: true }}
        >
          <Background gap={24} size={1} color="#27272a" />
          <Controls showInteractive={false} />
          {!isPhone && <MiniMap pannable zoomable nodeColor={(n) => ((n.data as SceneNodeData).chapter?.color as string) || '#3f3f46'} maskColor="rgba(0,0,0,0.6)" />}
        </ReactFlow>
        <div className="absolute top-2 right-2 left-2 flex flex-wrap items-center gap-2 rounded-lg border border-surface-700 bg-surface-900/95 p-1.5 shadow-lg md:top-3 md:right-auto md:left-3">
          <form
            onSubmit={(e) => {
              e.preventDefault()
              jumpTo(search)
            }}
            className="relative"
          >
            <Search className="pointer-events-none absolute top-1/2 left-2 size-3.5 -translate-y-1/2 text-zinc-500" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Find scene…"
              className="h-7 w-32 rounded-md sm:w-40 border border-surface-700 bg-surface-950 pr-2 pl-7 text-xs text-zinc-200 outline-none focus:border-accent-600"
            />
          </form>
          {data.chapters.length > 0 && (
            <Select className="h-7 w-40 text-xs" value={chapterFilter} onChange={(e) => setChapterFilter(e.target.value)}>
              <option value="">All chapters</option>
              {data.chapters.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.title || c.id}
                </option>
              ))}
              <option value="__none">No chapter</option>
            </Select>
          )}
          <Segmented
            value={direction}
            onChange={(d) => {
              setDirection(d)
              localStorage.setItem('cyoa.graphDir', d)
            }}
            options={[
              { value: 'TB', label: '↓', title: 'Top to bottom' },
              { value: 'LR', label: '→', title: 'Left to right' },
            ]}
          />
          <Button size="sm" icon={<LayoutGrid className="size-3.5" />} onClick={() => setConfirmLayout(true)}>
            Auto-arrange
          </Button>
          <Checkbox
            className="text-xs"
            checked={labels}
            onChange={(l) => {
              setLabels(l)
              localStorage.setItem('cyoa.graphLabels', l ? '1' : '0')
            }}
            label={<span className="flex items-center gap-1"><Tag className="size-3" /> labels</span>}
          />
        </div>
        <div className="pointer-events-none absolute bottom-3 left-1/2 hidden -translate-x-1/2 rounded bg-surface-900/90 px-2 py-1 text-[11px] text-zinc-500 md:block">
          Drag from a scene's bottom dot to another scene to add a choice, or to empty space to create a new scene.
          Dashed lines have conditions.
        </div>
      </div>
      {selectedScene && (
        <div
          className={cx(
            'flex flex-col bg-surface-950',
            isPhone ? 'fixed inset-0 z-30' : 'w-[min(560px,50%)] shrink-0 border-l border-surface-700',
          )}
        >
          <div className="flex items-center justify-between border-b border-surface-700 px-3 py-1.5">
            <span className="text-xs font-semibold tracking-wide text-zinc-400 uppercase">
              Edit scene
            </span>
            <Button size="sm" variant="ghost" icon={<X className="size-4" />} onClick={() => select(null)} aria-label="Close" />
          </div>
          <div className="min-h-0 flex-1">
            <SceneEditor key={selectedScene.pk} scene={selectedScene} compact />
          </div>
        </div>
      )}
      <Dialog
        open={confirmLayout}
        onOpenChange={setConfirmLayout}
        title="Auto-arrange all scenes?"
        description="Every scene is moved to a tidy layout. Positions you arranged by hand are replaced."
        footer={
          <>
            <Button onClick={() => setConfirmLayout(false)}>Cancel</Button>
            <Button variant="primary" onClick={autoLayout}>
              Arrange
            </Button>
          </>
        }
      />
    </div>
  )
}
