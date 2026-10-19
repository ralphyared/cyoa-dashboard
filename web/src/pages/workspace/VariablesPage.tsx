import { Plus, Sigma, Trash2 } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Button, Empty, Field, Input, Select } from '@/components/ui'
import { variableNameError } from '@/lib/format'
import { useGameActions, useMeta } from '@/lib/queries'
import type { Value, VarType, Variable } from '@/lib/types'
import { useWorkspace } from './context'
import { ConfirmDelete, PageShell, RenameButton, UnusedBadge, UsagePopover, useUnused } from './shared'

const TYPE_LABELS: Record<VarType, string> = { number: 'Number', bool: 'True / false', text: 'Text' }

function defaultFor(type: VarType): Value {
  return type === 'number' ? 0 : type === 'bool' ? false : ''
}

export function VariablesPage() {
  const { gameId } = useWorkspace()
  const meta = useMeta(gameId)
  const actions = useGameActions(gameId)
  const unused = useUnused('variable')
  const [name, setName] = useState('')
  const [type, setType] = useState<VarType>('number')
  const [touched, setTouched] = useState(false)
  const [deleting, setDeleting] = useState<Variable | null>(null)
  if (!meta) return null
  const variables = meta.variables
  const names = variables.map((v) => v.name)
  const nameError = variableNameError(name, names)

  const save = (next: Variable[]) => actions.updateMeta({ variables: next })
  const change = (index: number, changes: Partial<Variable>) =>
    save(variables.map((v, i) => (i === index ? { ...v, ...changes } : v)))

  function add(e: FormEvent) {
    e.preventDefault()
    setTouched(true)
    if (nameError) return
    save([...variables, { name, type, initial: defaultFor(type), min: null, max: null, label: '' }])
    setName('')
    setTouched(false)
  }

  return (
    <PageShell
      title="Variables"
      description={
        <>
          Numbers (health, gold, mana), true/false flags (met the wizard?) and text. Use them in
          conditions and effects, show them in text with <code className="text-accent-300">{'{gold}'}</code>, and
          in the status bar (Settings). Numbers can have a minimum and maximum, either a number or
          another variable (e.g. hp up to max_hp).
        </>
      }
    >
      {variables.length === 0 ? (
        <Empty icon={<Sigma className="size-10" />} title="No variables yet">
          Add one below, e.g. <code>hp</code> as a number.
        </Empty>
      ) : (
        <>
        <div className="hidden overflow-x-auto rounded-lg border border-surface-700 md:block">
          <table className="w-full text-sm">
            <thead className="bg-surface-900 text-left text-xs text-zinc-500">
              <tr>
                <th className="px-3 py-2 font-medium">Name</th>
                <th className="px-3 py-2 font-medium">Label</th>
                <th className="px-3 py-2 font-medium">Type</th>
                <th className="px-3 py-2 font-medium">Starts at</th>
                <th className="px-3 py-2 font-medium">Min</th>
                <th className="px-3 py-2 font-medium">Max</th>
                <th className="px-3 py-2" />
              </tr>
            </thead>
            <tbody className="divide-y divide-surface-800">
              {variables.map((v, i) => (
                <tr key={v.name} className="align-middle">
                  <td className="px-3 py-1.5 whitespace-nowrap">
                    <RenameButton kind="variable" current={v.name} taken={names} />
                    {unused.has(v.name) && <span className="ml-1.5"><UnusedBadge /></span>}
                  </td>
                  <td className="px-3 py-1.5">
                    <Input className="h-7 w-32" value={v.label} placeholder={v.name} onChange={(e) => change(i, { label: e.target.value })} />
                  </td>
                  <td className="px-3 py-1.5">
                    <TypeSelect value={v.type} onChange={(t) => change(i, { type: t, initial: defaultFor(t), min: null, max: null })} />
                  </td>
                  <td className="px-3 py-1.5">
                    <InitialInput variable={v} onChange={(initial) => change(i, { initial })} />
                  </td>
                  <td className="px-3 py-1.5">
                    {v.type === 'number' && <BoundInput value={v.min} variables={variables} self={v.name} onChange={(min) => change(i, { min })} />}
                  </td>
                  <td className="px-3 py-1.5">
                    {v.type === 'number' && <BoundInput value={v.max} variables={variables} self={v.name} onChange={(max) => change(i, { max })} />}
                  </td>
                  <td className="px-3 py-1.5 text-right whitespace-nowrap">
                    <UsagePopover kind="variable" name={v.name} compact />
                    <Button size="xs" variant="ghost" icon={<Trash2 className="size-3.5" />} aria-label="Delete" onClick={() => setDeleting(v)} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="flex flex-col gap-2 md:hidden">
          {variables.map((v, i) => (
            <div key={v.name} className="flex flex-col gap-2 rounded-lg border border-surface-700 bg-surface-900 p-3">
              <div className="flex items-center gap-2">
                <RenameButton kind="variable" current={v.name} taken={names} />
                {unused.has(v.name) && <UnusedBadge />}
                <div className="ml-auto flex">
                  <UsagePopover kind="variable" name={v.name} compact />
                  <Button size="xs" variant="ghost" icon={<Trash2 className="size-3.5" />} aria-label="Delete" onClick={() => setDeleting(v)} />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <Field label="Label">
                  <Input className="h-8" value={v.label} placeholder={v.name} onChange={(e) => change(i, { label: e.target.value })} />
                </Field>
                <Field label="Type">
                  <TypeSelect value={v.type} onChange={(t) => change(i, { type: t, initial: defaultFor(t), min: null, max: null })} />
                </Field>
                <Field label="Starts at">
                  <InitialInput variable={v} onChange={(initial) => change(i, { initial })} />
                </Field>
                {v.type === 'number' && (
                  <>
                    <Field label="Min">
                      <BoundInput value={v.min} variables={variables} self={v.name} onChange={(min) => change(i, { min })} />
                    </Field>
                    <Field label="Max">
                      <BoundInput value={v.max} variables={variables} self={v.name} onChange={(max) => change(i, { max })} />
                    </Field>
                  </>
                )}
              </div>
            </div>
          ))}
        </div>
        </>
      )}

      <form onSubmit={add} className="flex flex-wrap items-start gap-2">
        <Field error={touched && name ? nameError : null} className="w-full sm:w-56">
          <Input className="font-mono" placeholder="new_variable" value={name} onChange={(e) => setName(e.target.value.toLowerCase())} />
        </Field>
        <Select className="w-auto" value={type} onChange={(e) => setType(e.target.value as VarType)}>
          {Object.entries(TYPE_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </Select>
        <Button type="submit" icon={<Plus className="size-4" />} disabled={!name}>
          Add variable
        </Button>
      </form>

      <ConfirmDelete
        open={deleting !== null}
        onOpenChange={(o) => !o && setDeleting(null)}
        title={`Delete variable “${deleting?.name}”?`}
        description={
          deleting && !unused.has(deleting.name)
            ? 'It is still used somewhere; those places will show errors until you fix them.'
            : undefined
        }
        onConfirm={() => deleting && save(variables.filter((v) => v.name !== deleting.name))}
      />
    </PageShell>
  )
}

function TypeSelect({ value, onChange }: { value: VarType; onChange: (type: VarType) => void }) {
  return (
    <Select className="h-7 w-auto" value={value} onChange={(e) => onChange(e.target.value as VarType)}>
      {Object.entries(TYPE_LABELS).map(([type, label]) => (
        <option key={type} value={type}>
          {label}
        </option>
      ))}
    </Select>
  )
}

function InitialInput({ variable, onChange }: { variable: Variable; onChange: (value: Value) => void }) {
  if (variable.type === 'bool') {
    return (
      <Select className="h-7 w-auto" value={String(variable.initial)} onChange={(e) => onChange(e.target.value === 'true')}>
        <option value="false">false</option>
        <option value="true">true</option>
      </Select>
    )
  }
  if (variable.type === 'text') {
    return <Input className="h-7 w-32" value={String(variable.initial)} onChange={(e) => onChange(e.target.value)} />
  }
  return <NumberCell value={Number(variable.initial) || 0} onChange={onChange} />
}

function NumberCell({ value, onChange }: { value: number; onChange: (n: number) => void }) {
  const [text, setText] = useState(String(value))
  return (
    <Input
      type="number"
      className="h-7 w-20 font-mono"
      value={text}
      onChange={(e) => {
        setText(e.target.value)
        const n = Number(e.target.value)
        if (e.target.value.trim() !== '' && Number.isFinite(n)) onChange(n)
      }}
    />
  )
}

/** A min/max bound: empty, a number, or another number variable. */
function BoundInput({
  value,
  variables,
  self,
  onChange,
}: {
  value: number | string | null
  variables: Variable[]
  self: string
  onChange: (value: number | string | null) => void
}) {
  const others = variables.filter((v) => v.type === 'number' && v.name !== self)
  const mode = value === null ? 'none' : typeof value === 'string' ? 'var' : 'number'
  return (
    <div className="flex flex-wrap items-center gap-1">
      <Select
        className="h-7 w-auto max-w-full"
        value={mode === 'var' ? `var:${value}` : mode}
        onChange={(e) => {
          const v = e.target.value
          if (v === 'none') onChange(null)
          else if (v === 'number') onChange(typeof value === 'number' ? value : 0)
          else onChange(v.slice(4))
        }}
      >
        <option value="none">—</option>
        <option value="number">number</option>
        {others.map((o) => (
          <option key={o.name} value={`var:${o.name}`}>
            = {o.name}
          </option>
        ))}
      </Select>
      {mode === 'number' && <NumberCell value={value as number} onChange={onChange} />}
    </div>
  )
}
