export function relativeTime(iso: string, now = Date.now()): string {
  const then = new Date(iso).getTime()
  const seconds = Math.round((now - then) / 1000)
  if (seconds < 45) return 'just now'
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `${minutes} min ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours} h ago`
  const days = Math.round(hours / 24)
  if (days < 7) return `${days} d ago`
  return new Date(iso).toLocaleDateString()
}

export function dateTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  })
}

export function plural(n: number, word: string, many = `${word}s`): string {
  return `${n.toLocaleString()} ${n === 1 ? word : many}`
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

export function slugify(text: string, fallback = 'item'): string {
  const slug = text
    .normalize('NFKD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
    .slice(0, 48)
    .replace(/_+$/, '')
  return slug || fallback
}

export const SLUG_RE = /^[a-z0-9][a-z0-9_]*$/
export const VAR_NAME_RE = /^[a-z_][a-z0-9_]*$/
export const RESERVED = new Set([
  'and', 'or', 'not', 'true', 'false', 'has', 'count', 'visited', 'visits', 'min', 'max',
  'round', 'floor', 'ceil', 'abs', 'give', 'take',
])

export function variableNameError(name: string, taken: Iterable<string>): string | null {
  if (!name) return 'Required'
  if (!VAR_NAME_RE.test(name)) return 'Use lowercase letters, digits and _ (not starting with a digit)'
  if (RESERVED.has(name)) return `“${name}” is a reserved word`
  for (const t of taken) if (t === name) return 'Already used'
  return null
}

export function slugError(slug: string, taken: Iterable<string>): string | null {
  if (!slug) return 'Required'
  if (!SLUG_RE.test(slug)) return 'Use lowercase letters, digits and _'
  for (const t of taken) if (t === slug) return 'Already used'
  return null
}

export async function downloadFile(url: string) {
  const response = await fetch(url, { credentials: 'same-origin' })
  if (!response.ok) {
    let detail: unknown = null
    try {
      detail = (await response.json()).detail
    } catch {
      // ignore
    }
    throw Object.assign(new Error('download failed'), { status: response.status, detail })
  }
  const blob = await response.blob()
  const disposition = response.headers.get('content-disposition') ?? ''
  const name = /filename="([^"]+)"/.exec(disposition)?.[1] ?? 'download'
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = name
  document.body.appendChild(link)
  link.click()
  link.remove()
  setTimeout(() => URL.revokeObjectURL(link.href), 1000)
}
