// Mirrors the server's JSON shapes (see engine/src/cyoa/model.py and server store.py).

export type VarType = 'number' | 'bool' | 'text'
export type Value = number | boolean | string

export interface Variable {
  name: string
  type: VarType
  initial: Value
  min: number | string | null
  max: number | string | null
  label: string
}

export interface Item {
  id: string
  name: string
  description: string
  stackable: boolean
}

export interface Rule {
  id: string
  name: string
  condition: string
  effects: string
  goto: string | null
}

export interface Chapter {
  id: string
  title: string
  color: string | null
}

export type EndingKind = 'death' | 'victory' | 'neutral'

export interface Ending {
  kind: EndingKind
  title: string
}

export type LockedMode = 'hide' | 'show'

export interface Choice {
  id: string
  text: string
  target: string
  condition: string
  when_locked: LockedMode
  hint: string
  effects: string
  once: boolean
}

export interface Settings {
  title_art: string
  intro: string
  accent_color: string
  status_format: string
  show_scene_titles: boolean
  text_width: number
  typewriter: boolean
  typing_speed: number
}

export interface Meta {
  title: string
  author: string
  description: string
  version: string
  start_scene: string
  settings: Settings
  variables: Variable[]
  items: Item[]
  rules: Rule[]
  chapters: Chapter[]
}

export interface SceneFields {
  title: string
  chapter: string | null
  text: string
  art: string
  on_enter: string
  choices: Choice[]
  ending: Ending | null
  tags: string[]
  notes: string
  position: [number, number] | null
  /** Keys of warnings the author has hidden (missing on scenes saved before this existed). */
  hidden_warnings?: string[]
}

export interface Scene extends SceneFields {
  pk: number
  id: string
  rev: number
  sort: number
  updated_at: string
}

/** What the person looking may do with a game. */
export type Access = 'read' | 'edit' | 'owner'
/** Levels the owner can share a game at. */
export type ShareLevel = 'read' | 'edit'

export interface GameDetail {
  id: string
  access: Access
  rev: number
  created_at: string
  updated_at: string
  meta: Meta
  scenes: Scene[]
}

export interface GameSummary {
  id: string
  title: string
  author: string
  scenes: number
  words: number
  updated_at: string
  deleted_at: string | null
  /** Only in the games list (not the trash). */
  access?: Access
  /** For the owner: how many people the game is shared with. */
  shared_with?: number
}

export type Severity = 'error' | 'warning'

export interface Issue {
  severity: Severity
  code: string
  message: string
  scene?: string
  choice?: string
  rule?: string
  variable?: string
  item?: string
  chapter?: string
  field?: string
  start?: number
  end?: number
  /** Scene warnings only: identifies the warning for hiding it. */
  key?: string
  hidden?: boolean
}

export interface ChapterStats {
  scenes: number
  words: number
  endings: number
  choices: number
}

export interface Stats extends ChapterStats {
  chapters: Record<string, ChapterStats>
}

export interface IssuesResponse {
  issues: Issue[]
  stats: Stats
}

/** What useIssues gives: hidden warnings are split off so nothing else counts them. */
export interface IssuesData extends IssuesResponse {
  hidden: Issue[]
}

export type CheckMode = 'condition' | 'effects' | 'markup' | 'value'

export interface CheckError {
  message: string
  start: number
  end: number
}

export interface CheckResult {
  errors: CheckError[]
  ast: AstNode | null
  hint: string | null
}

export type AstNode =
  | { type: 'number'; value: number; span: [number, number] }
  | { type: 'string'; value: string; span: [number, number] }
  | { type: 'bool'; value: boolean; span: [number, number] }
  | { type: 'name'; name: string; span: [number, number] }
  | { type: 'call'; func: string; args: AstNode[]; span: [number, number] }
  | { type: 'unary'; op: string; operand: AstNode; span: [number, number] }
  | { type: 'binary'; op: string; left: AstNode; right: AstNode; span: [number, number] }
  | { type: 'assign'; target: string; op: string; value: AstNode; span: [number, number] }
  | { type: 'program'; statements: AstNode[] }

export interface Revision {
  id: number
  reason: string
  /** Who made the change (null for changes from before accounts existed). */
  by: string | null
  created_at: string
  updated_at: string
  snapshot: SceneFields & { id: string }
}

export interface TrashContents {
  games: GameSummary[]
  scenes: {
    pk: number
    id: string
    title: string
    game_id: string
    game_title: string
    deleted_at: string | null
  }[]
}

export interface Backup {
  name: string
  kind: 'auto' | 'manual'
  created_at: string
  size: number
}

export interface Reference {
  functions: { name: string; help: string; params: string[]; returns: string | null }[]
  colors: string[]
  styles: string[]
  keywords: string[]
}

export type RefKind = 'variable' | 'item' | 'scene' | 'chapter'

export interface Location {
  field: string
  scene?: string
  choice?: string
  rule?: string
  variable?: string
  start?: number
  end?: number
}

export interface PlaytestState {
  scene: string
  vars: Record<string, Value>
  inventory: Record<string, number>
  visits: Record<string, number>
  used_choices: string[]
  active_rules: string[]
  steps: number
}

export interface PlayerStatus {
  repo: string
  version: string | null
  checked_at: string | null
  platforms: { key: string; label: string; available: boolean }[]
}

// -- accounts and sharing ---------------------------------------------------------

export interface User {
  id: number
  username: string
  owner: boolean
}

export interface Me {
  authenticated: boolean
  user?: User
}

export interface Person extends User {
  created_at: string
  last_login_at: string | null
  games: { id: string; title: string; level: ShareLevel }[]
}

export interface Invite {
  id: number
  level: ShareLevel
  note: string
  created_at: string
  expires_at: string
}

export interface Sharing {
  people: { user_id: number; username: string; level: ShareLevel; since: string }[]
  invites: Invite[]
}

export interface InviteInfo {
  game_title: string
  level: ShareLevel
  user: User | null
}
