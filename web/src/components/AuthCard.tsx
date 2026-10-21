import { SquareTerminal } from 'lucide-react'
import type { FormEvent, ReactNode } from 'react'

/** The centered card used by the login, invite and password pages. */
export function AuthCard({ onSubmit, children }: { onSubmit?: (e: FormEvent) => void; children: ReactNode }) {
  return (
    <div className="flex h-full items-center justify-center overflow-y-auto p-4">
      <form
        onSubmit={onSubmit ?? ((e) => e.preventDefault())}
        className="flex w-full max-w-sm flex-col gap-4 rounded-xl border border-surface-700 bg-surface-900 p-6 shadow-2xl"
      >
        <div className="flex items-center gap-2.5">
          <SquareTerminal className="size-6 text-accent-400" />
          <h1 className="text-lg font-semibold text-zinc-100">CYOA Dashboard</h1>
        </div>
        {children}
      </form>
    </div>
  )
}

export function FormError({ children }: { children: ReactNode }) {
  return children ? <div className="text-sm text-red-400">{children}</div> : null
}
