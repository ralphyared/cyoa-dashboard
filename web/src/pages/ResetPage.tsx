import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { AuthCard, FormError } from '@/components/AuthCard'
import { Button, Field, Input, Spinner } from '@/components/ui'
import { api } from '@/lib/api'
import { errorText } from '@/lib/sharing'

const MIN_PASSWORD = 8

/** A password link the owner made for someone who forgot their password. */
export function ResetPage() {
  const { token = '' } = useParams()
  const qc = useQueryClient()
  const navigate = useNavigate()
  const info = useQuery({ queryKey: ['reset', token], queryFn: () => api.passwordReset(token), retry: false })
  const [password, setPassword] = useState('')
  const [repeat, setRepeat] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const tooShort = password.length > 0 && password.length < MIN_PASSWORD
  const mismatch = repeat.length > 0 && repeat !== password

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (tooShort || repeat !== password || !password) return
    setBusy(true)
    setError(null)
    try {
      await api.resetPassword(token, password)
      qc.clear()
      qc.setQueryData(['me'], await api.me())
      navigate('/', { replace: true })
    } catch (err) {
      setError(errorText(err))
      setBusy(false)
    }
  }

  if (info.isLoading) {
    return (
      <AuthCard>
        <Spinner />
      </AuthCard>
    )
  }
  if (!info.data) {
    return (
      <AuthCard>
        <p className="text-sm text-zinc-300">{errorText(info.error, 'This password link does not work.')}</p>
        <Link to="/login" className="text-sm text-accent-400 hover:underline">
          Log in
        </Link>
      </AuthCard>
    )
  }

  return (
    <AuthCard onSubmit={submit}>
      <p className="text-sm text-zinc-300">
        Choose a new password for <span className="font-semibold text-zinc-100">{info.data.username}</span>.
      </p>
      <Field label="New password" error={tooShort ? `At least ${MIN_PASSWORD} characters` : null}>
        <Input autoFocus type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} />
      </Field>
      <Field label="New password again" error={mismatch ? "The passwords don't match" : null}>
        <Input type="password" autoComplete="new-password" value={repeat} onChange={(e) => setRepeat(e.target.value)} />
      </Field>
      <FormError>{error}</FormError>
      <Button type="submit" variant="primary" loading={busy} disabled={!password || tooShort || repeat !== password}>
        Set password and log in
      </Button>
    </AuthCard>
  )
}
