import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { api } from './api'
import { useGame } from './queries'
import type { CheckMode, GameDetail } from './types'

export function useDebounced<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(timer)
  }, [value, delay])
  return debounced
}

/** What expressions may refer to: changes here invalidate earlier checks. */
export function environmentKey(game: GameDetail): string {
  return JSON.stringify([
    game.meta.variables.map((v) => [v.name, v.type, v.label]),
    game.meta.items.map((i) => [i.id, i.name]),
    game.scenes.map((s) => s.id),
  ])
}

/**
 * Parse and type-check source on the server as the author types (debounced).
 * Components checking the same text share one request through the query cache.
 */
export function useCheck(gameId: string, source: string, mode: CheckMode | 'plain') {
  const debounced = useDebounced(source, source ? 300 : 0)
  const envKey = useGame(gameId, environmentKey).data
  const query = useQuery({
    queryKey: ['check', gameId, mode, debounced, envKey],
    queryFn: () => api.check(gameId, debounced, mode as CheckMode),
    enabled: mode !== 'plain' && envKey !== undefined,
    staleTime: Infinity,
    gcTime: 60_000,
    placeholderData: keepPreviousData,
  })
  const current = !query.isPlaceholderData && debounced === source
  return { result: query.data, source: debounced, current }
}
