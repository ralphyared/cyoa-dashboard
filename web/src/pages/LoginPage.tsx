import { useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { Navigate, useNavigate, useSearchParams } from 'react-router'
import { AuthCard, FormError } from '@/components/AuthCard'
import { Button, Input } from '@/components/ui'
import { api } from '@/lib/api'
import { useMe } from '@/lib/queries'
import { errorText } from '@/lib/sharing'

/** Only same-site paths, so a crafted link can't send people elsewhere after logging in. */
function safeNext(next: string | null): string {
  return next && next.startsWith('/') && !next.startsWith('//') ? next : '/'
}

export function LoginPage() {
  const me = useMe()
  const qc = useQueryClient()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const next = safeNext(params.get('next'))

  if (me.data?.authenticated) return <Navigate to={next} replace />

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await api.login(username.trim(), password)
      qc.setQueryData(['me'], await api.me())
      navigate(next, { replace: true })
    } catch (err) {
      setError(errorText(err, 'Login failed'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <AuthCard onSubmit={submit}>
      <Input
        autoFocus
        autoComplete="username"
        autoCapitalize="none"
        spellCheck={false}
        placeholder="Username"
        aria-label="Username"
        value={username}
        onChange={(e) => setUsername(e.target.value)}
      />
      <Input
        type="password"
        autoComplete="current-password"
        placeholder="Password"
        aria-label="Password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
      />
      <FormError>{error}</FormError>
      <Button type="submit" variant="primary" loading={busy} disabled={!username.trim() || !password}>
        Log in
      </Button>
      <p className="text-xs text-zinc-500">
        Forgot your password? Ask the person who shared the game with you for a new password link.
      </p>
    </AuthCard>
  )
}
