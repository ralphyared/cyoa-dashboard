import { useQueryClient } from '@tanstack/react-query'
import { SquareTerminal } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Navigate, useNavigate, useSearchParams } from 'react-router'
import { Button, Input } from '@/components/ui'
import { api } from '@/lib/api'
import { useMe } from '@/lib/queries'

export function LoginPage() {
  const me = useMe()
  const qc = useQueryClient()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const next = params.get('next') || '/'
  const safeNext = next.startsWith('/') && !next.startsWith('//') ? next : '/'

  if (me.data?.authenticated) return <Navigate to={safeNext} replace />

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await api.login(password)
      qc.setQueryData(['me'], { authenticated: true })
      navigate(safeNext, { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex h-full items-center justify-center p-4">
      <form
        onSubmit={submit}
        className="flex w-full max-w-sm flex-col gap-4 rounded-xl border border-surface-700 bg-surface-900 p-6 shadow-2xl"
      >
        <div className="flex items-center gap-2.5">
          <SquareTerminal className="size-6 text-accent-400" />
          <h1 className="text-lg font-semibold text-zinc-100">CYOA Dashboard</h1>
        </div>
        <Input
          type="password"
          autoFocus
          autoComplete="current-password"
          placeholder="Password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        {error && <div className="text-sm text-red-400">{error}</div>}
        <Button type="submit" variant="primary" loading={busy} disabled={!password}>
          Log in
        </Button>
      </form>
    </div>
  )
}
