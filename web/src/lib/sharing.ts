import type { ShareLevel } from './types'

export const LEVELS: Record<ShareLevel, { label: string; help: string }> = {
  read: { label: 'Can read', help: 'read every scene and playtest' },
  edit: { label: 'Can edit', help: 'change anything in this game' },
}

export const LEVEL_OPTIONS = (Object.keys(LEVELS) as ShareLevel[]).map((value) => ({
  value,
  label: LEVELS[value].label,
}))

export function expiresText(iso: string): string {
  const days = Math.ceil((new Date(iso).getTime() - Date.now()) / 86_400_000)
  return days <= 1 ? 'expires within a day' : `expires in ${days} days`
}

export function errorText(err: unknown, fallback = 'Something went wrong'): string {
  return err instanceof Error ? err.message : fallback
}
