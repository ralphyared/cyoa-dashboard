import { createContext, useContext } from 'react'
import type { Issue } from '@/lib/types'

export type PanelKind = 'issues' | 'playtest'

export interface PlaytestRequest {
  scene?: string
  nonce: number
}

export interface WorkspaceState {
  gameId: string
  panel: PanelKind | null
  setPanel: (panel: PanelKind | null) => void
  /** Open the playtest panel and start playing (from a scene, or from the title screen). */
  playtest: (scene?: string) => void
  playtestRequest: PlaytestRequest | null
  openPalette: () => void
}

export const WorkspaceContext = createContext<WorkspaceState | null>(null)

export function useWorkspace(): WorkspaceState {
  const ctx = useContext(WorkspaceContext)
  if (!ctx) throw new Error('useWorkspace must be used inside the workspace')
  return ctx
}

export interface SceneIssueCounts {
  errors: number
  warnings: number
}

export function issuesByScene(issues: Issue[] | undefined): Map<string, SceneIssueCounts> {
  const map = new Map<string, SceneIssueCounts>()
  for (const issue of issues ?? []) {
    if (!issue.scene) continue
    const entry = map.get(issue.scene) ?? { errors: 0, warnings: 0 }
    if (issue.severity === 'error') entry.errors += 1
    else entry.warnings += 1
    map.set(issue.scene, entry)
  }
  return map
}
