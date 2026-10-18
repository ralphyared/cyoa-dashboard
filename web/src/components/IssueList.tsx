import { AlertTriangle, CircleAlert } from 'lucide-react'
import type { Issue } from '@/lib/types'

export function IssueList({ issues }: { issues: Issue[] }) {
  return (
    <ul className="flex flex-col gap-1 rounded-md border border-surface-700 bg-surface-900 px-3 py-2">
      {issues.map((issue, i) => (
        <li key={i} className="flex items-start gap-2 text-sm">
          {issue.severity === 'error' ? (
            <CircleAlert className="mt-0.5 size-3.5 shrink-0 text-red-400" />
          ) : (
            <AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-amber-400" />
          )}
          <span className={issue.severity === 'error' ? 'text-red-200' : 'text-amber-100/90'}>{issue.message}</span>
        </li>
      ))}
    </ul>
  )
}
