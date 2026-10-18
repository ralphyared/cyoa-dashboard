// Convert between expression syntax trees (from the server's /check endpoint)
// and the rows shown by the visual condition/effects builders. Anything the
// builder can't represent returns null, and the editor stays in code mode.

import type { AstNode, Value, Variable } from './types'

export type CmpOp = '==' | '!=' | '<' | '<=' | '>' | '>='
export const CMP_OPS: CmpOp[] = ['==', '!=', '>=', '>', '<=', '<']
export const CMP_LABELS: Record<CmpOp, string> = {
  '==': 'is',
  '!=': 'is not',
  '>=': '≥',
  '>': '>',
  '<=': '≤',
  '<': '<',
}
const FLIP: Record<CmpOp, CmpOp> = {
  '==': '==',
  '!=': '!=',
  '<': '>',
  '<=': '>=',
  '>': '<',
  '>=': '<=',
}

export type CondRow =
  | { kind: 'var'; name: string; op: CmpOp; value: Value }
  | { kind: 'has'; item: string; negate: boolean; count: number }
  | { kind: 'visited'; scene: string; negate: boolean }

export interface CondModel {
  join: 'and' | 'or'
  rows: CondRow[]
}

export type EffectRow =
  | { kind: 'set'; name: string; op: '=' | '+=' | '-='; value: Value }
  | { kind: 'give' | 'take'; item: string; count: number }

function isLiteral(node: AstNode): node is Extract<AstNode, { value: Value }> {
  return node.type === 'number' || node.type === 'string' || node.type === 'bool'
}

function flatten(node: AstNode, op: 'and' | 'or'): AstNode[] {
  if (node.type === 'binary' && node.op === op) {
    return [...flatten(node.left, op), ...flatten(node.right, op)]
  }
  return [node]
}

function stringArg(node: AstNode | undefined): string | null {
  return node && node.type === 'string' ? node.value : null
}

function rowFrom(node: AstNode): CondRow | null {
  if (node.type === 'name') return { kind: 'var', name: node.name, op: '==', value: true }
  if (node.type === 'unary' && node.op === 'not') {
    const inner = node.operand
    if (inner.type === 'name') return { kind: 'var', name: inner.name, op: '==', value: false }
    const row = rowFrom(inner)
    if (row && (row.kind === 'has' || row.kind === 'visited') && !row.negate) {
      return { ...row, negate: true }
    }
    return null
  }
  if (node.type === 'call') {
    if (node.func === 'has') {
      const item = stringArg(node.args[0])
      if (item === null) return null
      if (node.args.length === 1) return { kind: 'has', item, negate: false, count: 1 }
      const n = node.args[1]
      if (node.args.length === 2 && n.type === 'number' && Number.isInteger(n.value)) {
        return { kind: 'has', item, negate: false, count: n.value }
      }
      return null
    }
    if (node.func === 'visited' && node.args.length === 1) {
      const scene = stringArg(node.args[0])
      return scene === null ? null : { kind: 'visited', scene, negate: false }
    }
    return null
  }
  if (node.type === 'binary' && node.op in FLIP) {
    let op = node.op as CmpOp
    let subject = node.left
    let literal = node.right
    if (isLiteral(subject) && !isLiteral(literal)) {
      ;[subject, literal] = [literal, subject]
      op = FLIP[op]
    }
    if (!isLiteral(literal)) return null
    if (subject.type === 'name') return { kind: 'var', name: subject.name, op, value: literal.value }
    if (
      subject.type === 'call' &&
      subject.func === 'count' &&
      op === '>=' &&
      literal.type === 'number' &&
      Number.isInteger(literal.value)
    ) {
      const item = stringArg(subject.args[0])
      if (item !== null) return { kind: 'has', item, negate: false, count: literal.value }
    }
  }
  return null
}

export function conditionToModel(ast: AstNode | null): CondModel | null {
  if (ast === null) return { join: 'and', rows: [] }
  const ands = flatten(ast, 'and')
  const ors = flatten(ast, 'or')
  const [join, parts]: ['and' | 'or', AstNode[]] =
    ands.length > 1 ? ['and', ands] : ors.length > 1 ? ['or', ors] : ['and', [ast]]
  const rows = parts.map(rowFrom)
  return rows.every((r): r is CondRow => r !== null) ? { join, rows } : null
}

export function literal(value: Value): string {
  if (typeof value === 'string') return JSON.stringify(value)
  if (typeof value === 'boolean') return value ? 'true' : 'false'
  return Number.isFinite(value) ? String(value) : '0'
}

export function rowToText(row: CondRow): string {
  switch (row.kind) {
    case 'var':
      if (typeof row.value === 'boolean' && (row.op === '==' || row.op === '!=')) {
        const truthy = row.op === '==' ? row.value : !row.value
        return truthy ? row.name : `not ${row.name}`
      }
      return `${row.name} ${row.op} ${literal(row.value)}`
    case 'has': {
      const call =
        row.count > 1 ? `has(${JSON.stringify(row.item)}, ${row.count})` : `has(${JSON.stringify(row.item)})`
      return row.negate ? `not ${call}` : call
    }
    case 'visited': {
      const call = `visited(${JSON.stringify(row.scene)})`
      return row.negate ? `not ${call}` : call
    }
  }
}

export function modelToCondition(model: CondModel): string {
  return model.rows.map(rowToText).join(` ${model.join} `)
}

export function effectsToRows(ast: AstNode | null): EffectRow[] | null {
  if (ast === null) return []
  if (ast.type !== 'program') return null
  const rows: EffectRow[] = []
  for (const st of ast.statements) {
    if (st.type === 'assign') {
      if (!(st.op === '=' || st.op === '+=' || st.op === '-=') || !isLiteral(st.value)) return null
      rows.push({ kind: 'set', name: st.target, op: st.op, value: st.value.value })
    } else if (st.type === 'call' && (st.func === 'give' || st.func === 'take')) {
      const item = stringArg(st.args[0])
      if (item === null) return null
      let count = 1
      if (st.args.length === 2) {
        const n = st.args[1]
        if (n.type !== 'number' || !Number.isInteger(n.value)) return null
        count = n.value
      } else if (st.args.length !== 1) {
        return null
      }
      rows.push({ kind: st.func, item, count })
    } else {
      return null
    }
  }
  return rows
}

export function effectRowToText(row: EffectRow): string {
  if (row.kind === 'set') return `${row.name} ${row.op} ${literal(row.value)}`
  const item = JSON.stringify(row.item)
  return row.count === 1 ? `${row.kind}(${item})` : `${row.kind}(${item}, ${row.count})`
}

export function rowsToEffects(rows: EffectRow[]): string {
  return rows.map(effectRowToText).join('\n')
}

export function defaultValue(variable: Variable | undefined): Value {
  if (!variable) return 0
  if (variable.type === 'bool') return true
  if (variable.type === 'text') return ''
  return 0
}
