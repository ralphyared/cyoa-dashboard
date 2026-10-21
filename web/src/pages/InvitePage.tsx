import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { AuthCard, FormError } from '@/components/AuthCard'
import { Button, Field, Input, Spinner } from '@/components/ui'
import { api } from '@/lib/api'
import { LEVELS, errorText } from '@/lib/sharing'

const MIN_PASSWORD = 8

/** Opening an invite link: create an account, or add the game to the one you're logged in to. */
export function InvitePage() {
  const { token = '' } = useParams()
  const qc = useQueryClient()
  const navigate = useNavigate()
  const info = useQuery({ queryKey: ['invite', token], queryFn: () => api.invite(token), retry: false })
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [repeat, setRepeat] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function finish(action: () => Promise<{ game_id: string }>) {
    setBusy(true)
    setError(null)
    try {
      const { game_id } = await action()
      qc.setQueryData(['me'], await api.me())
      await qc.invalidateQueries({ queryKey: ['games'] })
      navigate(`/games/${game_id}`, { replace: true })
    } catch (err) {
      setError(errorText(err))
      setBusy(false)
    }
  }

  async function logout() {
    await api.logout()
    qc.clear()
    await info.refetch()
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
        <p className="text-sm text-zinc-300">{errorText(info.error, 'This invite link does not work.')}</p>
        <Link to="/login" className="text-sm text-accent-400 hover:underline">
          Log in
        </Link>
      </AuthCard>
    )
  }

  const { game_title, level, user } = info.data
  const what = (
    <p className="text-sm text-zinc-300">
      You've been invited to <span className="font-semibold text-zinc-100">“{game_title || 'Untitled'}”</span>. You'll
      be able to {LEVELS[level].help}.
    </p>
  )

  if (user?.owner) {
    return (
      <AuthCard>
        {what}
        <p className="text-sm text-zinc-400">
          You're logged in as the owner, so you already have this game. Send the link to the person it's for.
        </p>
        <Link to="/" className="text-sm text-accent-400 hover:underline">
          Back to your games
        </Link>
      </AuthCard>
    )
  }

  if (user) {
    return (
      <AuthCard onSubmit={(e) => {
        e.preventDefault()
        void finish(() => api.acceptInvite(token))
      }}>
        {what}
        <p className="text-sm text-zinc-400">
          It will be added to your account, <span className="text-zinc-200">{user.username}</span>.
        </p>
        <FormError>{error}</FormError>
        <Button type="submit" variant="primary" loading={busy}>
          Open the game
        </Button>
        <button type="button" className="text-left text-xs text-zinc-500 hover:text-zinc-300" onClick={() => void logout()}>
          Not you? Log out and use another account
        </button>
      </AuthCard>
    )
  }

  const tooShort = password.length > 0 && password.length < MIN_PASSWORD
  const mismatch = repeat.length > 0 && repeat !== password
  function join(e: FormEvent) {
    e.preventDefault()
    if (tooShort || mismatch || !username.trim() || !password) return
    void finish(() => api.joinInvite(token, username.trim(), password))
  }

  return (
    <AuthCard onSubmit={join}>
      {what}
      <p className="text-sm text-zinc-400">Choose a username and password for this dashboard.</p>
      <Field label="Username" hint="3–32 letters, digits, dots, dashes or underscores">
        <Input
          autoFocus
          autoComplete="username"
          autoCapitalize="none"
          spellCheck={false}
          value={username}
          onChange={(e) => setUsername(e.target.value)}
        />
      </Field>
      <Field label="Password" error={tooShort ? `At least ${MIN_PASSWORD} characters` : null}>
        <Input type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} />
      </Field>
      <Field label="Password again" error={mismatch ? "The passwords don't match" : null}>
        <Input type="password" autoComplete="new-password" value={repeat} onChange={(e) => setRepeat(e.target.value)} />
      </Field>
      <FormError>{error}</FormError>
      <Button
        type="submit"
        variant="primary"
        loading={busy}
        disabled={!username.trim() || !password || tooShort || repeat !== password}
      >
        Create account and open the game
      </Button>
      <p className="text-xs text-zinc-500">
        Already have an account?{' '}
        <Link to={`/login?next=${encodeURIComponent(`/invite/${token}`)}`} className="text-accent-400 hover:underline">
          Log in
        </Link>{' '}
        to add the game to it.
      </p>
    </AuthCard>
  )
}
