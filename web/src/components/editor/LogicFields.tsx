// Condition and effect fields: a visual builder for the common cases, with the
// code editor always one click away. Builder edits write plain expression text.

import { Code2, ListChecks, Plus, X } from 'lucide-react'
import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import {
  CMP_LABELS,
  CMP_OPS,
  conditionToModel,
  defaultValue,
  effectsToRows,
  modelToCondition,
  rowsToEffects,
  type CmpOp,
  type CondModel,
  type CondRow,
  type EffectRow,
} from '@/lib/builder'
import { useMeta } from '@/lib/queries'
import type { CheckResult, Item, Value, Variable } from '@/lib/types'
import { useCheck } from '@/lib/useCheck'
import { ScenePicker } from '../ScenePicker'
import { Button, Input, Segmented, Select, cx } from '../ui'
import { CodeEditor } from './CodeEditor'

type FieldMode = 'builder' | 'code'

function useLogicMode<T>(
  gameId: string,
  value: string,
  checkMode: 'condition' | 'effects',
  convert: (result: CheckResult) => T | null,
  empty: T,
) {
  const check = useCheck(gameId, value, checkMode)
  const [mode, setMode] = useState<FieldMode | null>(value.trim() ? null : 'builder')
  const [model, setModel] = useState<T | null>(value.trim() ? null : empty)
  const emitted = useRef<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  useEffect(() => {
    if (value === emitted.current) return
    if (!value.trim()) {
      setModel(empty)
      setMode((m) => m ?? 'builder')
      return
    }
    if (!check.current || !check.result) return
    const converted = check.result.errors.length === 0 ? convert(check.result) : null
    if (converted) {
      setModel(converted)
      setMode((m) => m ?? 'builder')
    } else {
      setMode('code')
    }
    // `convert` and `empty` are stable per field type
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value, check.current, check.result])

  function switchTo(next: FieldMode) {
    setNotice(null)
    if (next === 'code') {
      setMode('code')
      return
    }
    if (!value.trim()) {
      setModel(empty)
      setMode('builder')
      return
    }
    const converted =
      check.current && check.result && check.result.errors.length === 0 ? convert(check.result) : null
    if (converted) {
      setModel(converted)
      setMode('builder')
    } else {
      setNotice(
        check.result?.errors.length
          ? 'Fix the errors first to use the builder.'
          : 'This is too complex for the builder; edit it as code.',
      )
    }
  }

  const markEmitted = useCallback((text: string | null) => {
    emitted.current = text
  }, [])

  return { check, mode, model, setModel, markEmitted, switchTo, notice }
}

function ModeToggle({ mode, onChange }: { mode: FieldMode | null; onChange: (m: FieldMode) => void }) {
  return (
    <Segmented
      size="xs"
      value={mode ?? 'code'}
      onChange={onChange}
      options={[
        { value: 'builder', label: <ListChecks className="size-3.5" />, title: 'Builder' },
        { value: 'code', label: <Code2 className="size-3.5" />, title: 'Code' },
      ]}
    />
  )
}

function Errors({ result, current }: { result?: CheckResult; current: boolean }) {
  if (!result || !current || result.errors.length === 0) return null
  return (
    <ul className="mt-1 space-y-0.5">
      {result.errors.map((e, i) => (
        <li key={i} className="text-xs text-red-400">
          {e.message}
        </li>
      ))}
    </ul>
  )
}

function FieldShell({
  label,
  mode,
  onMode,
  children,
  footer,
  notice,
}: {
  label: ReactNode
  mode: FieldMode | null
  onMode: (m: FieldMode) => void
  children: ReactNode
  footer?: ReactNode
  notice?: string | null
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center justify-between gap-2">
        <div className="text-xs font-medium text-zinc-400">{label}</div>
        <ModeToggle mode={mode} onChange={onMode} />
      </div>
      {children}
      {notice && <div className="text-xs text-amber-300">{notice}</div>}
      {footer}
    </div>
  )
}

// -- conditions ------------------------------------------------------------------------

const EMPTY_CONDITION: CondModel = { join: 'and', rows: [] }
const toCondition = (r: CheckResult) => conditionToModel(r.ast)

export function ConditionField({
  gameId,
  value,
  onChange,
  label = 'Condition',
  placeholder = 'e.g. gold >= 10 and has("rope")',
  emptyText = 'Always available',
  footer,
}: {
  gameId: string
  value: string
  onChange: (value: string) => void
  label?: ReactNode
  placeholder?: string
  emptyText?: string
  footer?: (result: CheckResult | undefined) => ReactNode
}) {
  const meta = useMeta(gameId)
  const { check, mode, model, setModel, markEmitted, switchTo, notice } = useLogicMode(
    gameId, value, 'condition', toCondition, EMPTY_CONDITION,
  )

  function update(next: CondModel) {
    setModel(next)
    const text = modelToCondition(next)
    markEmitted(text)
    onChange(text)
  }

  return (
    <FieldShell label={label} mode={mode} onMode={switchTo} notice={notice} footer={
      <>
        <Errors result={check.result} current={check.current} />
        {footer?.(check.current ? check.result : undefined)}
      </>
    }>
      {mode === 'builder' && model && meta ? (
        <div className="flex flex-col gap-1.5">
          {model.rows.length === 0 && <div className="text-xs text-zinc-500 italic">{emptyText}</div>}
          {model.rows.map((row, i) => (
            <div key={i} className="flex items-center gap-1.5">
              <span className="w-9 shrink-0 text-right text-[11px] font-medium text-zinc-500 uppercase">
                {i === 0 ? 'if' : model.join}
              </span>
              <CondRowEditor
                gameId={gameId}
                row={row}
                variables={meta.variables}
                items={meta.items}
                onChange={(r) => update({ ...model, rows: model.rows.map((x, j) => (j === i ? r : x)) })}
              />
              <Button
                size="xs"
                variant="ghost"
                icon={<X className="size-3.5" />}
                aria-label="Remove condition"
                onClick={() => update({ ...model, rows: model.rows.filter((_, j) => j !== i) })}
              />
            </div>
          ))}
          <div className="flex items-center gap-2">
            <Button
              size="xs"
              variant="ghost"
              icon={<Plus className="size-3.5" />}
              onClick={() => update({ ...model, rows: [...model.rows, newCondRow(meta.variables, meta.items)] })}
            >
              Add condition
            </Button>
            {model.rows.length > 1 && (
              <Segmented
                size="xs"
                value={model.join}
                onChange={(join) => update({ ...model, join })}
                options={[
                  { value: 'and', label: 'all must be true' },
                  { value: 'or', label: 'any can be true' },
                ]}
              />
            )}
          </div>
        </div>
      ) : (
        <CodeEditor
          gameId={gameId}
          mode="condition"
          value={value}
          onChange={(v) => {
            markEmitted(null)
            onChange(v)
          }}
          singleLine
          placeholder={placeholder}
        />
      )}
    </FieldShell>
  )
}

function newCondRow(variables: Variable[], items: Item[]): CondRow {
  const variable = variables[0]
  if (variable) {
    return {
      kind: 'var',
      name: variable.name,
      op: variable.type === 'number' ? '>=' : '==',
      value: variable.type === 'number' ? 1 : defaultValue(variable),
    }
  }
  if (items[0]) return { kind: 'has', item: items[0].id, negate: false, count: 1 }
  return { kind: 'visited', scene: '', negate: false }
}

function subjectKey(row: CondRow): string {
  return row.kind === 'var' ? `var:${row.name}` : row.kind
}

function CondRowEditor({
  gameId,
  row,
  variables,
  items,
  onChange,
}: {
  gameId: string
  row: CondRow
  variables: Variable[]
  items: Item[]
  onChange: (row: CondRow) => void
}) {
  function setSubject(key: string) {
    if (key.startsWith('var:')) {
      const v = variables.find((x) => `var:${x.name}` === key)
      onChange({
        kind: 'var',
        name: key.slice(4),
        op: v?.type === 'number' ? '>=' : '==',
        value: v?.type === 'number' ? 1 : defaultValue(v),
      })
    } else if (key === 'has') {
      onChange({ kind: 'has', item: items[0]?.id ?? '', negate: false, count: 1 })
    } else {
      onChange({ kind: 'visited', scene: '', negate: false })
    }
  }

  const variable = row.kind === 'var' ? variables.find((v) => v.name === row.name) : undefined
  return (
    <div className="flex min-w-0 flex-1 flex-wrap items-center gap-1.5">
      <Select className="h-7 w-auto max-w-44 text-xs" value={subjectKey(row)} onChange={(e) => setSubject(e.target.value)}>
        {row.kind === 'var' && !variable && <option value={`var:${row.name}`}>{row.name} (missing)</option>}
        {variables.length > 0 && (
          <optgroup label="Variables">
            {variables.map((v) => (
              <option key={v.name} value={`var:${v.name}`}>
                {v.label || v.name}
              </option>
            ))}
          </optgroup>
        )}
        <optgroup label="Other">
          <option value="has">Inventory</option>
          <option value="visited">Visited scene</option>
        </optgroup>
      </Select>

      {row.kind === 'var' && (variable?.type ?? 'number') === 'number' && (
        <>
          <Select className="h-7 w-auto text-xs" value={row.op} onChange={(e) => onChange({ ...row, op: e.target.value as CmpOp })}>
            {CMP_OPS.map((op) => (
              <option key={op} value={op}>
                {CMP_LABELS[op]}
              </option>
            ))}
          </Select>
          <NumberInput value={Number(row.value) || 0} onChange={(n) => onChange({ ...row, value: n })} />
        </>
      )}
      {row.kind === 'var' && variable?.type === 'bool' && (
        <Select
          className="h-7 w-auto text-xs"
          value={String(row.op === '==' ? row.value : !row.value)}
          onChange={(e) => onChange({ ...row, op: '==', value: e.target.value === 'true' })}
        >
          <option value="true">is true</option>
          <option value="false">is false</option>
        </Select>
      )}
      {row.kind === 'var' && variable?.type === 'text' && (
        <>
          <Select className="h-7 w-auto text-xs" value={row.op === '!=' ? '!=' : '=='} onChange={(e) => onChange({ ...row, op: e.target.value as CmpOp })}>
            <option value="==">is</option>
            <option value="!=">is not</option>
          </Select>
          <Input className="h-7 w-32 text-xs" value={String(row.value)} onChange={(e) => onChange({ ...row, value: e.target.value })} />
        </>
      )}

      {row.kind === 'has' && (
        <>
          <Select className="h-7 w-auto text-xs" value={row.negate ? 'no' : 'yes'} onChange={(e) => onChange({ ...row, negate: e.target.value === 'no' })}>
            <option value="yes">has</option>
            <option value="no">doesn't have</option>
          </Select>
          {!row.negate && (
            <NumberInput value={row.count} min={1} onChange={(n) => onChange({ ...row, count: Math.max(1, Math.round(n)) })} title="How many" />
          )}
          <ItemSelect items={items} value={row.item} onChange={(item) => onChange({ ...row, item })} />
        </>
      )}

      {row.kind === 'visited' && (
        <>
          <Select className="h-7 w-auto text-xs" value={row.negate ? 'no' : 'yes'} onChange={(e) => onChange({ ...row, negate: e.target.value === 'no' })}>
            <option value="yes">has been to</option>
            <option value="no">hasn't been to</option>
          </Select>
          <ScenePicker gameId={gameId} size="sm" className="w-48" value={row.scene} onChange={(scene) => onChange({ ...row, scene })} />
        </>
      )}
    </div>
  )
}

function NumberInput({
  value,
  onChange,
  min,
  title,
}: {
  value: number
  onChange: (n: number) => void
  min?: number
  title?: string
}) {
  const [text, setText] = useState(String(value))
  useEffect(() => {
    if (Number(text) !== value) setText(String(value))
    // only resync when the value changes from outside
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value])
  return (
    <Input
      type="number"
      title={title}
      min={min}
      className="h-7 w-20 text-xs"
      value={text}
      onChange={(e) => {
        setText(e.target.value)
        const n = Number(e.target.value)
        if (e.target.value.trim() !== '' && Number.isFinite(n)) onChange(n)
      }}
    />
  )
}

function ItemSelect({ items, value, onChange }: { items: Item[]; value: string; onChange: (id: string) => void }) {
  const known = items.some((i) => i.id === value)
  return (
    <Select className={cx('h-7 w-auto max-w-44 text-xs', !known && 'border-red-500/60')} value={value} onChange={(e) => onChange(e.target.value)}>
      {!known && <option value={value}>{value ? `${value} (missing)` : 'choose item…'}</option>}
      {items.map((i) => (
        <option key={i.id} value={i.id}>
          {i.name || i.id}
        </option>
      ))}
    </Select>
  )
}

// -- effects -----------------------------------------------------------------------------

const EMPTY_EFFECTS: EffectRow[] = []
const toEffects = (r: CheckResult) => effectsToRows(r.ast)

export function EffectsField({
  gameId,
  value,
  onChange,
  label = 'Effects',
  placeholder = 'e.g. gold -= 10\ngive("rope")',
  emptyText = 'Nothing changes',
}: {
  gameId: string
  value: string
  onChange: (value: string) => void
  label?: ReactNode
  placeholder?: string
  emptyText?: string
}) {
  const meta = useMeta(gameId)
  const { check, mode, model, setModel, markEmitted, switchTo, notice } = useLogicMode(
    gameId, value, 'effects', toEffects, EMPTY_EFFECTS,
  )

  function update(rows: EffectRow[]) {
    setModel(rows)
    const text = rowsToEffects(rows)
    markEmitted(text)
    onChange(text)
  }

  return (
    <FieldShell label={label} mode={mode} onMode={switchTo} notice={notice} footer={<Errors result={check.result} current={check.current} />}>
      {mode === 'builder' && model && meta ? (
        <div className="flex flex-col gap-1.5">
          {model.length === 0 && <div className="text-xs text-zinc-500 italic">{emptyText}</div>}
          {model.map((row, i) => (
            <div key={i} className="flex items-center gap-1.5">
              <EffectRowEditor
                row={row}
                variables={meta.variables}
                items={meta.items}
                onChange={(r) => update(model.map((x, j) => (j === i ? r : x)))}
              />
              <Button
                size="xs"
                variant="ghost"
                icon={<X className="size-3.5" />}
                aria-label="Remove effect"
                onClick={() => update(model.filter((_, j) => j !== i))}
              />
            </div>
          ))}
          <div className="flex gap-1">
            <Button
              size="xs"
              variant="ghost"
              icon={<Plus className="size-3.5" />}
              disabled={meta.variables.length === 0}
              title={meta.variables.length === 0 ? 'Add variables first' : undefined}
              onClick={() => {
                const v = meta.variables[0]
                update([...model, {
                  kind: 'set', name: v.name, op: v.type === 'number' ? '-=' : '=',
                  value: v.type === 'number' ? 1 : defaultValue(v),
                }])
              }}
            >
              Change variable
            </Button>
            <Button
              size="xs"
              variant="ghost"
              icon={<Plus className="size-3.5" />}
              disabled={meta.items.length === 0}
              title={meta.items.length === 0 ? 'Add items first' : undefined}
              onClick={() => update([...model, { kind: 'give', item: meta.items[0].id, count: 1 }])}
            >
              Give / take item
            </Button>
          </div>
        </div>
      ) : (
        <CodeEditor
          gameId={gameId}
          mode="effects"
          value={value}
          onChange={(v) => {
            markEmitted(null)
            onChange(v)
          }}
          placeholder={placeholder}
        />
      )}
    </FieldShell>
  )
}

function EffectRowEditor({
  row,
  variables,
  items,
  onChange,
}: {
  row: EffectRow
  variables: Variable[]
  items: Item[]
  onChange: (row: EffectRow) => void
}) {
  if (row.kind !== 'set') {
    return (
      <div className="flex flex-1 flex-wrap items-center gap-1.5">
        <Select className="h-7 w-auto text-xs" value={row.kind} onChange={(e) => onChange({ ...row, kind: e.target.value as 'give' | 'take' })}>
          <option value="give">Give</option>
          <option value="take">Take away</option>
        </Select>
        <NumberInput value={row.count} min={1} onChange={(n) => onChange({ ...row, count: Math.max(1, Math.round(n)) })} title="How many" />
        <ItemSelect items={items} value={row.item} onChange={(item) => onChange({ ...row, item })} />
      </div>
    )
  }
  return <SetRowEditor row={row} variables={variables} onChange={onChange} />
}

type SetRow = Extract<EffectRow, { kind: 'set' }>

function SetRowEditor({
  row,
  variables,
  onChange,
}: {
  row: SetRow
  variables: Variable[]
  onChange: (row: EffectRow) => void
}) {
  const variable = variables.find((v) => v.name === row.name)
  const type = variable?.type ?? 'number'
  const setVariable = (name: string) => {
    const v = variables.find((x) => x.name === name)
    onChange({
      kind: 'set', name,
      op: v?.type === 'number' ? row.op : '=',
      value: v?.type === type ? row.value : defaultValue(v),
    })
  }
  return (
    <div className="flex flex-1 flex-wrap items-center gap-1.5">
      <Select className={cx('h-7 w-auto max-w-44 text-xs', !variable && 'border-red-500/60')} value={row.name} onChange={(e) => setVariable(e.target.value)}>
        {!variable && <option value={row.name}>{row.name} (missing)</option>}
        {variables.map((v) => (
          <option key={v.name} value={v.name}>
            {v.label || v.name}
          </option>
        ))}
      </Select>
      {type === 'number' ? (
        <>
          <Select className="h-7 w-auto text-xs" value={row.op} onChange={(e) => onChange({ ...row, op: e.target.value as '=' | '+=' | '-=' })}>
            <option value="-=">decrease by</option>
            <option value="+=">increase by</option>
            <option value="=">set to</option>
          </Select>
          <NumberInput value={Number(row.value) || 0} onChange={(n) => onChange({ ...row, value: n })} />
        </>
      ) : type === 'bool' ? (
        <Select className="h-7 w-auto text-xs" value={String(row.value)} onChange={(e) => onChange({ ...row, op: '=', value: e.target.value === 'true' })}>
          <option value="true">set to true</option>
          <option value="false">set to false</option>
        </Select>
      ) : (
        <>
          <span className="text-xs text-zinc-400">set to</span>
          <Input className="h-7 w-40 text-xs" value={String(row.value)} onChange={(e) => onChange({ ...row, op: '=', value: e.target.value as Value })} />
        </>
      )}
    </div>
  )
}
