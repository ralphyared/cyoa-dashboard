// Autosave: edits update the cached game immediately and are sent to the server
// shortly after the author stops typing. Each scene (and the game's settings)
// saves independently, with optimistic concurrency via `rev`.

import type { QueryClient } from '@tanstack/react-query'
import { ApiError, api } from './api'
import type { GameDetail, Meta, Scene, SceneFields } from './types'

export type SaveStatus = 'saved' | 'pending' | 'saving' | 'error' | 'conflict'

export interface SaveState {
  status: SaveStatus
  message?: string
  theirs?: Scene
}

const DEBOUNCE_MS = 700
const RETRY_MS = 5000
const SAVED: SaveState = { status: 'saved' }

type Key = string // "meta" or "scene:<pk>"

export class SaveManager {
  private pending = new Map<Key, Record<string, unknown>>()
  private inflight = new Set<Key>()
  private timers = new Map<Key, ReturnType<typeof setTimeout>>()
  private forced = new Set<Key>()
  private states = new Map<Key, SaveState>()
  private listeners = new Set<() => void>()
  private issuesTimer: ReturnType<typeof setTimeout> | null = null
  private qc: QueryClient
  readonly gameId: string

  constructor(qc: QueryClient, gameId: string) {
    this.qc = qc
    this.gameId = gameId
  }

  // -- subscription (for useSyncExternalStore) --------------------------------

  subscribe = (listener: () => void) => {
    this.listeners.add(listener)
    return () => {
      this.listeners.delete(listener)
    }
  }

  state(key: Key): SaveState {
    return this.states.get(key) ?? SAVED
  }

  overall(): SaveStatus {
    let worst: SaveStatus = 'saved'
    const rank: Record<SaveStatus, number> = {
      saved: 0,
      pending: 1,
      saving: 2,
      error: 3,
      conflict: 4,
    }
    for (const s of this.states.values()) if (rank[s.status] > rank[worst]) worst = s.status
    return worst
  }

  private overallSnapshot: SaveStatus = 'saved'
  overallStatus = () => this.overallSnapshot

  hasUnsaved(): boolean {
    return this.pending.size > 0 || this.inflight.size > 0
  }

  private set(key: Key, state: SaveState) {
    if (state.status === 'saved') this.states.delete(key)
    else this.states.set(key, state)
    this.overallSnapshot = this.overall()
    for (const listener of this.listeners) listener()
  }

  // -- cache helpers ---------------------------------------------------------------

  private game(): GameDetail | undefined {
    return this.qc.getQueryData<GameDetail>(['game', this.gameId])
  }

  private patchCache(update: (game: GameDetail) => GameDetail) {
    this.qc.setQueryData<GameDetail>(['game', this.gameId], (game) => (game ? update(game) : game))
  }

  private refreshIssues() {
    if (this.issuesTimer) clearTimeout(this.issuesTimer)
    this.issuesTimer = setTimeout(() => {
      void this.qc.invalidateQueries({ queryKey: ['issues', this.gameId] })
    }, 400)
  }

  // -- public API ----------------------------------------------------------------------

  updateScene(pk: number, changes: Partial<SceneFields>) {
    this.patchCache((game) => ({
      ...game,
      scenes: game.scenes.map((s) => (s.pk === pk ? { ...s, ...changes } : s)),
    }))
    this.queue(`scene:${pk}`, changes)
  }

  updateMeta(changes: Partial<Meta>) {
    this.patchCache((game) => ({ ...game, meta: { ...game.meta, ...changes } }))
    this.queue('meta', changes)
  }

  /** Resolve a conflict by sending our version over theirs. */
  keepMine(key: Key) {
    this.forced.add(key)
    const state = this.state(key)
    if (state.theirs && key.startsWith('scene:')) {
      const theirs = state.theirs
      this.patchCache((game) => ({
        ...game,
        scenes: game.scenes.map((s) => (s.pk === theirs.pk ? { ...s, rev: theirs.rev } : s)),
      }))
    }
    void this.flush(key)
  }

  /** Resolve a conflict by dropping our unsent changes and taking the server's version. */
  useTheirs(key: Key) {
    this.pending.delete(key)
    const theirs = this.state(key).theirs
    if (theirs) {
      this.patchCache((game) => ({
        ...game,
        scenes: game.scenes.map((s) => (s.pk === theirs.pk ? theirs : s)),
      }))
    } else {
      void this.qc.invalidateQueries({ queryKey: ['game', this.gameId] })
    }
    this.set(key, SAVED)
  }

  /** Forget a scene that was deleted (or replaced after a rename). */
  forget(key: Key) {
    this.pending.delete(key)
    const timer = this.timers.get(key)
    if (timer) clearTimeout(timer)
    this.timers.delete(key)
    this.set(key, SAVED)
  }

  async flushAll(): Promise<void> {
    const keys = [...new Set([...this.pending.keys(), ...this.timers.keys()])]
    await Promise.all(keys.map((key) => this.flush(key)))
  }

  // -- internals ----------------------------------------------------------------------

  private queue(key: Key, changes: Record<string, unknown>) {
    this.pending.set(key, { ...(this.pending.get(key) ?? {}), ...changes })
    if (this.state(key).status !== 'conflict') this.set(key, { status: 'pending' })
    this.schedule(key, DEBOUNCE_MS)
  }

  private schedule(key: Key, delay: number) {
    const existing = this.timers.get(key)
    if (existing) clearTimeout(existing)
    this.timers.set(
      key,
      setTimeout(() => {
        this.timers.delete(key)
        void this.flush(key)
      }, delay),
    )
  }

  private async flush(key: Key): Promise<void> {
    const timer = this.timers.get(key)
    if (timer) {
      clearTimeout(timer)
      this.timers.delete(key)
    }
    if (this.inflight.has(key)) return
    if (this.state(key).status === 'conflict' && !this.forced.has(key)) return
    const changes = this.pending.get(key)
    if (!changes) return
    this.pending.delete(key)
    const force = this.forced.delete(key)
    this.inflight.add(key)
    this.set(key, { status: 'saving' })
    try {
      if (key === 'meta') await this.sendMeta(changes, force)
      else await this.sendScene(Number(key.slice(6)), changes, force)
      this.set(key, this.pending.has(key) ? { status: 'pending' } : SAVED)
      this.refreshIssues()
    } catch (error) {
      // put the changes back underneath anything typed since
      this.pending.set(key, { ...changes, ...(this.pending.get(key) ?? {}) })
      if (error instanceof ApiError && error.status === 409) {
        const detail = error.detail as { scene?: Scene } | null
        this.set(key, {
          status: 'conflict',
          message: 'Changed elsewhere (another tab?)',
          theirs: detail && typeof detail === 'object' ? detail.scene : undefined,
        })
        return
      }
      if (error instanceof ApiError && error.status === 404) {
        this.forget(key)
        return
      }
      const message = error instanceof Error ? error.message : 'save failed'
      this.set(key, { status: 'error', message })
      if (!(error instanceof ApiError && error.status === 422)) this.schedule(key, RETRY_MS)
    } finally {
      this.inflight.delete(key)
      if (this.pending.has(key) && this.state(key).status === 'pending') {
        this.schedule(key, DEBOUNCE_MS)
      }
    }
  }

  private async sendScene(pk: number, changes: Record<string, unknown>, force: boolean) {
    const current = this.game()?.scenes.find((s) => s.pk === pk)
    const body = force ? changes : { ...changes, rev: current?.rev }
    const result = await api.updateScene(this.gameId, pk, body)
    if ('scene' in result) {
      const saved = result.scene
      const unsent = this.pending.get(`scene:${pk}`) ?? {}
      this.patchCache((game) => ({
        ...game,
        scenes: game.scenes.map((s) =>
          s.pk === pk ? { ...s, ...saved, ...unsent, rev: saved.rev } : s,
        ),
      }))
    } else {
      this.qc.setQueryData(['game', this.gameId], result.game)
    }
  }

  private async sendMeta(changes: Record<string, unknown>, force: boolean) {
    const rev = this.game()?.rev
    const result = await api.updateMeta(this.gameId, force ? changes : { ...changes, rev })
    const unsent = this.pending.get('meta') ?? {}
    this.patchCache((game) => ({
      ...game,
      rev: result.rev,
      meta: { ...result.meta, ...(unsent as Partial<Meta>) },
    }))
  }
}
