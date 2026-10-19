import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Archive, Download, Plus } from 'lucide-react'
import { useState } from 'react'
import { AppHeader } from '@/components/AppHeader'
import { Badge, Button, Empty, Spinner } from '@/components/ui'
import { api } from '@/lib/api'
import { dateTime, downloadFile, formatBytes } from '@/lib/format'

export function BackupsPage() {
  const qc = useQueryClient()
  const backups = useQuery({ queryKey: ['backups'], queryFn: api.backups })
  const [busy, setBusy] = useState(false)

  async function create() {
    setBusy(true)
    try {
      await api.createBackup()
      await qc.invalidateQueries({ queryKey: ['backups'] })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex h-full flex-col">
      <AppHeader />
      <main className="mx-auto w-full max-w-3xl flex-1 overflow-y-auto px-4 py-6 sm:px-6 sm:py-8">
        <div className="mb-2 flex items-center justify-between">
          <h1 className="text-xl font-semibold text-zinc-100">Backups</h1>
          <Button variant="primary" icon={<Plus className="size-4" />} loading={busy} onClick={() => void create()}>
            Back up now
          </Button>
        </div>
        <p className="mb-6 text-sm text-zinc-500">
          A snapshot of everything is taken automatically once a day (the last 14 are kept). To
          move a single game elsewhere, use “Export project backup” on the games page instead.
        </p>
        {backups.isLoading && <Spinner />}
        {backups.data?.length === 0 && <Empty icon={<Archive className="size-10" />} title="No backups yet" />}
        <div className="flex flex-col gap-2">
          {backups.data?.map((b) => (
            <div key={b.name} className="flex items-center gap-3 rounded-md border border-surface-700 bg-surface-900 px-3 py-2">
              <Badge tone={b.kind === 'auto' ? 'neutral' : 'accent'}>{b.kind}</Badge>
              <div className="flex-1 text-sm text-zinc-200">{dateTime(b.created_at)}</div>
              <div className="text-xs text-zinc-500">{formatBytes(b.size)}</div>
              <Button size="sm" variant="ghost" icon={<Download className="size-3.5" />} onClick={() => void downloadFile(api.backupUrl(b.name))}>
                Download
              </Button>
            </div>
          ))}
        </div>
      </main>
    </div>
  )
}
