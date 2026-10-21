import { useQuery, useQueryClient } from '@tanstack/react-query'
import { createContext, useCallback, useContext, useMemo, useSyncExternalStore } from 'react'
import { api } from './api'
import type { SaveManager, SaveState, SaveStatus } from './save'
import type { Access, GameDetail, Issue, IssuesData, IssuesResponse, Meta, Scene, SceneFields } from './types'

export const gameKey = (gameId: string) => ['game', gameId] as const
export const issuesKey = (gameId: string) => ['issues', gameId] as const

export function useMe() {
  return useQuery({ queryKey: ['me'], queryFn: api.me, staleTime: 60_000 })
}

export function useGames() {
  return useQuery({ queryKey: ['games'], queryFn: api.games })
}

export function useGame<T = GameDetail>(gameId: string, select?: (game: GameDetail) => T) {
  return useQuery({
    queryKey: gameKey(gameId),
    queryFn: () => api.game(gameId),
    select,
    staleTime: Infinity, // the cache is the editing copy; refetched explicitly
  })
}

/** What the logged-in person may do with this game. */
export function useAccess(gameId: string): Access | undefined {
  return useGame(gameId, (g) => g.access).data
}

export function useMeta(gameId: string): Meta | undefined {
  return useGame(gameId, (g) => g.meta).data
}

export function useScenes(gameId: string): Scene[] {
  return useGame(gameId, (g) => g.scenes).data ?? EMPTY
}
const EMPTY: Scene[] = []

export function useScene(gameId: string, pk: number | null): Scene | undefined {
  const select = useCallback(
    (g: GameDetail) => (pk === null ? undefined : g.scenes.find((s) => s.pk === pk)),
    [pk],
  )
  return useGame(gameId, select).data
}

export function useIssues(gameId: string) {
  return useQuery({ queryKey: issuesKey(gameId), queryFn: () => api.issues(gameId), select: splitHidden })
}

function splitHidden(data: IssuesResponse): IssuesData {
  return { ...data, issues: data.issues.filter((i) => !i.hidden), hidden: data.issues.filter((i) => i.hidden) }
}

export function useReference() {
  return useQuery({ queryKey: ['reference'], queryFn: api.reference, staleTime: Infinity })
}

// -- autosave context -----------------------------------------------------------------

export const SaveContext = createContext<SaveManager | null>(null)

export function useSaver(): SaveManager {
  const saver = useContext(SaveContext)
  if (!saver) throw new Error('useSaver needs a SaveContext provider')
  return saver
}

export function useSaveState(key: string): SaveState {
  const saver = useSaver()
  return useSyncExternalStore(saver.subscribe, () => saver.state(key))
}

export function useOverallSaveStatus(): SaveStatus {
  const saver = useSaver()
  return useSyncExternalStore(saver.subscribe, saver.overallStatus)
}

// -- actions that aren't plain autosaved edits ----------------------------------------

export function useGameActions(gameId: string) {
  const qc = useQueryClient()
  const saver = useSaver()
  return useMemo(() => {
    const setGame = (update: (g: GameDetail) => GameDetail) =>
      qc.setQueryData<GameDetail>(gameKey(gameId), (g) => (g ? update(g) : g))
    const refreshIssues = () => qc.invalidateQueries({ queryKey: issuesKey(gameId) })
    const replaceGame = (game: GameDetail) => {
      qc.setQueryData(gameKey(gameId), game)
      void refreshIssues()
    }

    return {
      updateScene: (pk: number, changes: Partial<SceneFields>) => saver.updateScene(pk, changes),
      updateMeta: (changes: Partial<Meta>) => saver.updateMeta(changes),

      /** Hide a scene warning the author has checked, or show it again. */
      setWarningHidden(issue: Issue, hidden: boolean) {
        const scene = qc.getQueryData<GameDetail>(gameKey(gameId))?.scenes.find((s) => s.id === issue.scene)
        const issues = qc.getQueryData<IssuesResponse>(issuesKey(gameId))
        if (!scene || !issue.key || !issues) return
        const sameWarning = (i: Issue) => i.scene === issue.scene && i.key === issue.key
        // Keep only keys that still match a warning, so outdated ones drop out.
        const keys = new Set(issues.issues.filter((i) => i.scene === scene.id && i.hidden && i.key).map((i) => i.key!))
        if (hidden) keys.add(issue.key)
        else keys.delete(issue.key)
        qc.setQueryData<IssuesResponse>(issuesKey(gameId), (data) =>
          data && { ...data, issues: data.issues.map((i) => (sameWarning(i) ? { ...i, hidden } : i)) },
        )
        saver.updateScene(scene.pk, { hidden_warnings: [...keys] })
      },

      async createScene(fields: Partial<SceneFields> & { id?: string }): Promise<Scene> {
        const scene = await api.createScene(gameId, fields)
        setGame((g) => ({ ...g, scenes: [...g.scenes, scene] }))
        void refreshIssues()
        return scene
      },

      async deleteScene(pk: number) {
        saver.forget(`scene:${pk}`)
        await api.deleteScene(gameId, pk)
        setGame((g) => ({ ...g, scenes: g.scenes.filter((s) => s.pk !== pk) }))
        void refreshIssues()
      },

      /** Rename a scene id; every reference is updated server-side. */
      async renameScene(pk: number, newId: string) {
        await saver.flushAll()
        const result = await api.updateScene(gameId, pk, { id: newId })
        if ('game' in result) replaceGame(result.game)
      },

      async rename(kind: 'variable' | 'item' | 'chapter', old: string, newName: string) {
        await saver.flushAll()
        replaceGame(await api.rename(gameId, kind, old, newName))
      },

      async setPositions(positions: Record<number, [number, number]>) {
        setGame((g) => ({
          ...g,
          scenes: g.scenes.map((s) => (positions[s.pk] ? { ...s, position: positions[s.pk] } : s)),
        }))
        await api.setPositions(gameId, positions)
      },

      async setOrder(order: number[]) {
        const rank = new Map(order.map((pk, i) => [pk, i + 1]))
        setGame((g) => ({
          ...g,
          scenes: g.scenes
            .map((s) => ({ ...s, sort: rank.get(s.pk) ?? s.sort }))
            .sort((a, b) => a.sort - b.sort || a.pk - b.pk),
        }))
        await api.setOrder(gameId, order)
      },

      async restoreRevision(pk: number, revisionId: number) {
        saver.forget(`scene:${pk}`)
        const scene = await api.restoreRevision(gameId, pk, revisionId)
        setGame((g) => ({ ...g, scenes: g.scenes.map((s) => (s.pk === pk ? scene : s)) }))
        void refreshIssues()
      },

      async reload() {
        await saver.flushAll()
        await qc.invalidateQueries({ queryKey: gameKey(gameId) })
        void refreshIssues()
      },
    }
  }, [gameId, qc, saver])
}
