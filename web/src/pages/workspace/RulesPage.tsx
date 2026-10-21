import { ArrowDown, ArrowUp, GitBranch, Plus, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { ConditionField, EffectsField } from '@/components/editor/LogicFields'
import { ScenePicker } from '@/components/ScenePicker'
import { Button, Empty, Field, Input, useReadOnly } from '@/components/ui'
import { useGameActions, useIssues, useMeta } from '@/lib/queries'
import type { Rule } from '@/lib/types'
import { useWorkspace } from './context'
import { IssueList } from '@/components/IssueList'
import { ConfirmDelete, PageShell } from './shared'

function newRuleId(rules: Rule[]): string {
  let n = rules.length + 1
  while (rules.some((r) => r.id === `r${n}`)) n++
  return `r${n}`
}

export function RulesPage() {
  const { gameId } = useWorkspace()
  const meta = useMeta(gameId)
  const actions = useGameActions(gameId)
  const issues = useIssues(gameId).data?.issues ?? []
  const [deleting, setDeleting] = useState<Rule | null>(null)
  const readOnly = useReadOnly()
  if (!meta) return null
  const rules = meta.rules
  const save = (next: Rule[]) => actions.updateMeta({ rules: next })
  const change = (index: number, changes: Partial<Rule>) =>
    save(rules.map((r, i) => (i === index ? { ...r, ...changes } : r)))
  const move = (index: number, delta: number) => {
    const next = [...rules]
    const [rule] = next.splice(index, 1)
    next.splice(index + delta, 0, rule)
    save(next)
  }

  return (
    <PageShell
      title="Rules"
      description={
        <>
          Rules watch the game everywhere. A rule fires once when its condition becomes true (after
          any effect), applies its effects, and can send the player to a scene. The classic example:
          when <code className="text-accent-300">hp &lt;= 0</code>, go to your death scene. A rule fires again
          only after its condition has been false in between.
        </>
      }
      actions={
        !readOnly && (
          <Button
            variant="primary"
            icon={<Plus className="size-4" />}
            onClick={() => save([...rules, { id: newRuleId(rules), name: '', condition: '', effects: '', goto: null }])}
          >
            Add rule
          </Button>
        )
      }
    >
      {rules.length === 0 && <Empty icon={<GitBranch className="size-10" />} title="No rules yet" />}
      {rules.map((rule, i) => {
        const ruleIssues = issues.filter((x) => x.rule === rule.id)
        return (
          <div key={rule.id} className="flex flex-col gap-4 rounded-lg border border-surface-700 bg-surface-900 p-3 sm:p-4">
            <div className="flex items-center gap-2">
              <Input
                className="flex-1 font-medium"
                value={rule.name}
                placeholder="Rule name (for you), e.g. Death"
                onChange={(e) => change(i, { name: e.target.value })}
              />
              {!readOnly && (
                <>
                  <Button size="sm" variant="ghost" icon={<ArrowUp className="size-3.5" />} disabled={i === 0} onClick={() => move(i, -1)} aria-label="Move up" />
                  <Button size="sm" variant="ghost" icon={<ArrowDown className="size-3.5" />} disabled={i === rules.length - 1} onClick={() => move(i, 1)} aria-label="Move down" />
                  <Button size="sm" variant="ghost" icon={<Trash2 className="size-3.5" />} onClick={() => setDeleting(rule)} aria-label="Delete rule" />
                </>
              )}
            </div>
            <ConditionField
              gameId={gameId}
              label="When this becomes true…"
              emptyText="Add a condition, otherwise this rule never fires"
              value={rule.condition}
              onChange={(condition) => change(i, { condition })}
            />
            <EffectsField gameId={gameId} label="…apply these effects" value={rule.effects} onChange={(effects) => change(i, { effects })} />
            <Field label="…and then go to">
              <ScenePicker
                gameId={gameId}
                className="w-full sm:w-72"
                value={rule.goto ?? ''}
                allowNone="Stay where the player is"
                onChange={(goto) => change(i, { goto: goto || null })}
              />
            </Field>
            {ruleIssues.length > 0 && <IssueList issues={ruleIssues} />}
          </div>
        )
      })}
      <ConfirmDelete
        open={deleting !== null}
        onOpenChange={(o) => !o && setDeleting(null)}
        title={`Delete rule “${deleting?.name || deleting?.condition || 'untitled'}”?`}
        onConfirm={() => deleting && save(rules.filter((r) => r.id !== deleting.id))}
      />
    </PageShell>
  )
}
