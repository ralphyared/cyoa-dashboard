import type {
  Backup,
  CheckMode,
  CheckResult,
  GameDetail,
  GameSummary,
  Invite,
  InviteInfo,
  IssuesResponse,
  Location,
  Me,
  Meta,
  Person,
  PlayerStatus,
  RefKind,
  Reference,
  Revision,
  Scene,
  SceneFields,
  ShareLevel,
  Sharing,
  TrashContents,
  User,
} from './types'

export class ApiError extends Error {
  status: number
  detail: unknown

  constructor(status: number, message: string, detail: unknown) {
    super(message)
    this.status = status
    this.detail = detail
  }
}

function messageFrom(detail: unknown, fallback: string): string {
  if (typeof detail === 'string') return detail
  if (detail && typeof detail === 'object' && 'message' in detail) {
    return String((detail as { message: unknown }).message)
  }
  if (Array.isArray(detail) && detail[0]?.msg) return String(detail[0].msg)
  return fallback
}

let onUnauthorized: (() => void) | null = null

export function setUnauthorizedHandler(handler: () => void) {
  onUnauthorized = handler
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const response = await fetch(path, {
    method,
    headers: body === undefined ? {} : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
    credentials: 'same-origin',
  })
  if (!response.ok) {
    let detail: unknown = null
    try {
      detail = (await response.json()).detail
    } catch {
      // not JSON
    }
    if (response.status === 401 && !path.startsWith('/api/login')) onUnauthorized?.()
    throw new ApiError(response.status, messageFrom(detail, response.statusText), detail)
  }
  return (await response.json()) as T
}

const get = <T>(path: string) => request<T>('GET', path)
const post = <T>(path: string, body?: unknown) => request<T>('POST', path, body ?? {})
const patch = <T>(path: string, body: unknown) => request<T>('PATCH', path, body)
const del = <T>(path: string) => request<T>('DELETE', path)

const g = (gameId: string) => `/api/games/${encodeURIComponent(gameId)}`

export type ScenePatch = Partial<SceneFields> & { id?: string; rev?: number }
export type SceneUpdateResult = { scene: Scene } | { game: GameDetail }

export const api = {
  me: () => get<Me>('/api/me'),
  login: (username: string, password: string) => post<{ ok: boolean }>('/api/login', { username, password }),
  logout: () => post<{ ok: boolean }>('/api/logout'),
  renameAccount: (username: string) => patch<User>('/api/me', { username }),
  changePassword: (current: string, newPassword: string) =>
    post<{ ok: boolean }>('/api/me/password', { current, new: newPassword }),

  people: () => get<Person[]>('/api/users'),
  removePerson: (userId: number) => del<{ ok: boolean }>(`/api/users/${userId}`),
  resetLink: (userId: number) =>
    post<{ token: string; username: string; expires_at: string }>(`/api/users/${userId}/reset-link`),
  sharing: (gameId: string) => get<Sharing>(`${g(gameId)}/sharing`),
  createInvite: (gameId: string, level: ShareLevel, note: string) =>
    post<Invite & { token: string }>(`${g(gameId)}/invites`, { level, note }),
  cancelInvite: (gameId: string, inviteId: number) => del<{ ok: boolean }>(`${g(gameId)}/invites/${inviteId}`),
  setLevel: (gameId: string, userId: number, level: ShareLevel) =>
    request<{ ok: boolean }>('PUT', `${g(gameId)}/people/${userId}`, { level }),
  removeAccess: (gameId: string, userId: number) => del<{ ok: boolean }>(`${g(gameId)}/people/${userId}`),

  invite: (token: string) => get<InviteInfo>(`/api/invites/${encodeURIComponent(token)}`),
  acceptInvite: (token: string) => post<{ game_id: string }>(`/api/invites/${encodeURIComponent(token)}/accept`),
  joinInvite: (token: string, username: string, password: string) =>
    post<{ game_id: string }>(`/api/invites/${encodeURIComponent(token)}/join`, { username, password }),
  passwordReset: (token: string) => get<{ username: string }>(`/api/password-resets/${encodeURIComponent(token)}`),
  resetPassword: (token: string, password: string) =>
    post<{ ok: boolean }>(`/api/password-resets/${encodeURIComponent(token)}`, { password }),

  games: () => get<GameSummary[]>('/api/games'),
  createGame: (title: string) => post<GameDetail>('/api/games', { title }),
  game: (gameId: string) => get<GameDetail>(g(gameId)),
  updateMeta: (gameId: string, changes: Partial<Meta> & { rev?: number }) =>
    patch<{ rev: number; meta: Meta }>(g(gameId), changes),
  deleteGame: (gameId: string) => del<{ ok: boolean }>(g(gameId)),
  duplicateGame: (gameId: string) => post<GameDetail>(`${g(gameId)}/duplicate`),
  importGame: (data: unknown) => post<GameDetail>('/api/games/import', data),
  exportUrl: (gameId: string, format: 'player' | 'project') =>
    `${g(gameId)}/export?format=${format}`,
  standaloneUrl: (gameId: string, platform: string) =>
    `${g(gameId)}/standalone?platform=${encodeURIComponent(platform)}`,
  players: () => get<PlayerStatus>('/api/players'),
  updatePlayers: () => post<PlayerStatus>('/api/players/update'),

  createScene: (gameId: string, fields: Partial<SceneFields> & { id?: string }) =>
    post<Scene>(`${g(gameId)}/scenes`, fields),
  updateScene: (gameId: string, pk: number, changes: ScenePatch) =>
    patch<SceneUpdateResult>(`${g(gameId)}/scenes/${pk}`, changes),
  deleteScene: (gameId: string, pk: number) => del<{ ok: boolean }>(`${g(gameId)}/scenes/${pk}`),
  setPositions: (gameId: string, positions: Record<number, [number, number]>) =>
    post<{ ok: boolean }>(`${g(gameId)}/scenes/positions`, { positions }),
  setOrder: (gameId: string, order: number[]) =>
    post<{ ok: boolean }>(`${g(gameId)}/scenes/order`, { order }),
  revisions: (gameId: string, pk: number) =>
    get<Revision[]>(`${g(gameId)}/scenes/${pk}/revisions`),
  restoreRevision: (gameId: string, pk: number, revisionId: number) =>
    post<Scene>(`${g(gameId)}/scenes/${pk}/revisions/${revisionId}/restore`),

  issues: (gameId: string) => get<IssuesResponse>(`${g(gameId)}/issues`),
  check: (gameId: string, source: string, mode: CheckMode) =>
    post<CheckResult>(`${g(gameId)}/check`, { source, mode }),
  rename: (gameId: string, kind: RefKind, old: string, newName: string) =>
    post<GameDetail>(`${g(gameId)}/rename`, { kind, old, new: newName }),
  references: (gameId: string, kind: RefKind, name: string) =>
    get<{ references: Location[] }>(
      `${g(gameId)}/references?kind=${kind}&name=${encodeURIComponent(name)}`,
    ),
  reference: () => get<Reference>('/api/reference'),

  trash: () => get<TrashContents>('/api/trash'),
  restoreGame: (gameId: string) => post<{ ok: boolean }>(`/api/trash/games/${gameId}/restore`),
  purgeGame: (gameId: string) => del<{ ok: boolean }>(`/api/trash/games/${gameId}`),
  restoreScene: (pk: number) => post<Scene>(`/api/trash/scenes/${pk}/restore`),
  purgeScene: (pk: number) => del<{ ok: boolean }>(`/api/trash/scenes/${pk}`),

  backups: () => get<Backup[]>('/api/backups'),
  createBackup: () => post<Backup>('/api/backups'),
  backupUrl: (name: string) => `/api/backups/${encodeURIComponent(name)}`,
}
