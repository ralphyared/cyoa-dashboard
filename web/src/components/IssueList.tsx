import { AlertTriangle, CircleAlert, Eye, EyeOff } from 'lucide-react'
import { useState } from 'react'
import { Button } from '@/components/ui'
import { plural } from '@/lib/format'
import type { Issue } from '@/lib/types'

/** ``onHide`` adds a Hide button to warnings that can be hidden. */
export function IssueList({ issues, onHide }: { issues: Issue[]; onHide?: (issue: Issue) => void }) {
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
          {onHide && issue.key && (
            <Button
              size="xs"
              variant="ghost"
              className="-my-0.5 ml-auto shrink-0 text-zinc-400"
              icon={<EyeOff className="size-3.5" />}
              title="I've checked this: hide the warning (it comes back if this changes)"
              onClick={() => onHide(issue)}
            >
              Hide
            </Button>
          )}
        </li>
      ))}
    </ul>
  )
}

/** A scene's hidden warnings, folded into one line that opens to show them again. */
export function HiddenIssues({ issues, onShow }: { issues: Issue[]; onShow?: (issue: Issue) => void }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="text-xs text-zinc-500">
      <button
        type="button"
        className="flex items-center gap-1.5 hover:text-zinc-300"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
      >
        <EyeOff className="size-3.5" /> {plural(issues.length, 'hidden warning')}
      </button>
      {open && (
        <ul className="mt-1 flex flex-col gap-1 rounded-md border border-surface-700 px-3 py-2">
          {issues.map((issue, i) => (
            <li key={i} className="flex items-start gap-2 text-sm">
              <span className="text-zinc-400">{issue.message}</span>
              {onShow && (
                <Button
                  size="xs"
                  variant="ghost"
                  className="-my-0.5 ml-auto shrink-0 text-zinc-400"
                  icon={<Eye className="size-3.5" />}
                  onClick={() => onShow(issue)}
                >
                  Show again
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
