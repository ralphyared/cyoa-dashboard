import { useQueryClient } from '@tanstack/react-query'
import { Archive, BookOpen, LogOut, SquareTerminal, Trash2 } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link, NavLink } from 'react-router'
import { api } from '@/lib/api'
import { Button, cx } from './ui'

export function AppHeader({ children }: { children?: ReactNode }) {
  const qc = useQueryClient()
  async function logout() {
    await api.logout()
    qc.clear()
    qc.setQueryData(['me'], { authenticated: false })
  }
  const link = ({ isActive }: { isActive: boolean }) =>
    cx(
      'flex h-8 items-center gap-1.5 rounded-md px-2.5 text-sm',
      isActive ? 'bg-surface-800 text-zinc-100' : 'text-zinc-400 hover:text-zinc-100',
    )
  return (
    <header className="flex h-12 shrink-0 items-center gap-2 border-b border-surface-700 bg-surface-900 px-3 sm:gap-3 sm:px-4">
      <Link to="/" className="flex items-center gap-2 font-semibold text-zinc-100">
        <SquareTerminal className="size-5 text-accent-400" />
        <span className="hidden sm:inline">CYOA Dashboard</span>
      </Link>
      <nav className="flex items-center gap-1 sm:ml-4">
        <NavLink to="/" end className={link}>
          <BookOpen className="size-3.5" /> Games
        </NavLink>
        <NavLink to="/trash" className={link}>
          <Trash2 className="size-3.5" /> <span className="hidden sm:inline">Trash</span>
        </NavLink>
        <NavLink to="/backups" className={link}>
          <Archive className="size-3.5" /> <span className="hidden sm:inline">Backups</span>
        </NavLink>
      </nav>
      <div className="ml-auto flex items-center gap-2">
        {children}
        <Button variant="ghost" size="sm" icon={<LogOut className="size-3.5" />} onClick={() => void logout()} aria-label="Log out">
          <span className="hidden sm:inline">Log out</span>
        </Button>
      </div>
    </header>
  )
}
