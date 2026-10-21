import { useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { AppHeader } from '@/components/AppHeader'
import { FormError } from '@/components/AuthCard'
import { Button, Field, Input } from '@/components/ui'
import { api } from '@/lib/api'
import { useMe } from '@/lib/queries'
import { errorText } from '@/lib/sharing'

const MIN_PASSWORD = 8

export function AccountPage() {
  const me = useMe()
  const user = me.data?.user
  return (
    <div className="flex h-full flex-col">
      <AppHeader />
      <main className="mx-auto flex w-full max-w-xl flex-1 flex-col gap-8 overflow-y-auto px-4 py-6 sm:px-6 sm:py-8">
        <h1 className="text-xl font-semibold text-zinc-100">Your account</h1>
        {user && <UsernameForm key={user.id} username={user.username} />}
        {user?.owner ? (
          <section className="flex flex-col gap-1">
            <h2 className="text-sm font-semibold text-zinc-200">Password</h2>
            <p className="text-sm text-zinc-500">
              As the owner, your password is <code className="text-accent-300">CYOA_PASSWORD</code> in the
              server's <code className="text-accent-300">.env</code> file. Change it there and restart the
              dashboard.
            </p>
          </section>
        ) : (
          user && <PasswordForm />
        )}
      </main>
    </div>
  )
}

function UsernameForm({ username }: { username: string }) {
  const qc = useQueryClient()
  const [value, setValue] = useState(username)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)
  const [busy, setBusy] = useState(false)

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const user = await api.renameAccount(value.trim())
      qc.setQueryData(['me'], { authenticated: true, user })
      setValue(user.username)
      setSaved(true)
    } catch (err) {
      setError(errorText(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-3">
      <Field label="Username" hint="What you log in with. Others you share games with see it too.">
        <Input
          autoCapitalize="none"
          spellCheck={false}
          value={value}
          onChange={(e) => {
            setValue(e.target.value)
            setSaved(false)
          }}
        />
      </Field>
      <FormError>{error}</FormError>
      <div className="flex items-center gap-3">
        <Button type="submit" loading={busy} disabled={!value.trim() || value.trim().toLowerCase() === username}>
          Change username
        </Button>
        {saved && <span className="text-sm text-emerald-400">Saved</span>}
      </div>
    </form>
  )
}

function PasswordForm() {
  const [current, setCurrent] = useState('')
  const [password, setPassword] = useState('')
  const [repeat, setRepeat] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)
  const [busy, setBusy] = useState(false)
  const tooShort = password.length > 0 && password.length < MIN_PASSWORD
  const mismatch = repeat.length > 0 && repeat !== password

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (!current || tooShort || repeat !== password || !password) return
    setBusy(true)
    setError(null)
    try {
      await api.changePassword(current, password)
      setSaved(true)
      setCurrent('')
      setPassword('')
      setRepeat('')
    } catch (err) {
      setError(errorText(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-3">
      <h2 className="text-sm font-semibold text-zinc-200">Change password</h2>
      <Field label="Current password">
        <Input type="password" autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} />
      </Field>
      <Field label="New password" error={tooShort ? `At least ${MIN_PASSWORD} characters` : null}>
        <Input type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} />
      </Field>
      <Field label="New password again" error={mismatch ? "The passwords don't match" : null}>
        <Input type="password" autoComplete="new-password" value={repeat} onChange={(e) => setRepeat(e.target.value)} />
      </Field>
      <FormError>{error}</FormError>
      <div className="flex items-center gap-3">
        <Button type="submit" loading={busy} disabled={!current || !password || tooShort || repeat !== password}>
          Change password
        </Button>
        {saved && <span className="text-sm text-emerald-400">Changed. Other devices were logged out.</span>}
      </div>
    </form>
  )
}
