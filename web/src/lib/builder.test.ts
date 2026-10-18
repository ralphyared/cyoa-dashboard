import { describe, expect, it } from 'vitest'
import {
  conditionToModel,
  effectsToRows,
  modelToCondition,
  rowsToEffects,
} from './builder'
import type { AstNode } from './types'

const span: [number, number] = [0, 0]
const name = (n: string): AstNode => ({ type: 'name', name: n, span })
const num = (value: number): AstNode => ({ type: 'number', value, span })
const str = (value: string): AstNode => ({ type: 'string', value, span })
const bool = (value: boolean): AstNode => ({ type: 'bool', value, span })
const call = (func: string, ...args: AstNode[]): AstNode => ({ type: 'call', func, args, span })
const bin = (op: string, left: AstNode, right: AstNode): AstNode => ({ type: 'binary', op, left, right, span })
const not = (operand: AstNode): AstNode => ({ type: 'unary', op: 'not', operand, span })
const assign = (target: string, op: string, value: AstNode): AstNode => ({ type: 'assign', target, op, value, span })

describe('conditions', () => {
  it('converts simple comparisons and joins', () => {
    const ast = bin('and', bin('>=', name('gold'), num(10)), call('has', str('rope')))
    const model = conditionToModel(ast)
    expect(model).toEqual({
      join: 'and',
      rows: [
        { kind: 'var', name: 'gold', op: '>=', value: 10 },
        { kind: 'has', item: 'rope', negate: false, count: 1 },
      ],
    })
    expect(modelToCondition(model!)).toBe('gold >= 10 and has("rope")')
  })

  it('flips literal-first comparisons', () => {
    expect(conditionToModel(bin('<', num(3), name('hp')))?.rows[0]).toEqual({
      kind: 'var', name: 'hp', op: '>', value: 3,
    })
  })

  it('handles flags, negation, counts and visits', () => {
    const ast = bin(
      'or',
      bin('or', name('met_king'), not(call('has', str('key')))),
      bin('or', bin('>=', call('count', str('arrow')), num(3)), not(call('visited', str('cave')))),
    )
    const model = conditionToModel(ast)!
    expect(model.join).toBe('or')
    expect(modelToCondition(model)).toBe(
      'met_king or not has("key") or has("arrow", 3) or not visited("cave")',
    )
  })

  it('writes boolean rows naturally', () => {
    expect(modelToCondition({ join: 'and', rows: [{ kind: 'var', name: 'f', op: '==', value: false }] })).toBe('not f')
    expect(modelToCondition({ join: 'and', rows: [{ kind: 'var', name: 'f', op: '!=', value: false }] })).toBe('f')
    expect(conditionToModel(bin('==', name('f'), bool(true)))?.rows[0]).toEqual({
      kind: 'var', name: 'f', op: '==', value: true,
    })
  })

  it('quotes text values', () => {
    expect(modelToCondition({ join: 'and', rows: [{ kind: 'var', name: 'cls', op: '==', value: 'say "hi"' }] })).toBe(
      'cls == "say \\"hi\\""',
    )
  })

  it('refuses mixed and/or and arithmetic', () => {
    expect(conditionToModel(bin('or', bin('and', name('a'), name('b')), name('c')))).toBeNull()
    expect(conditionToModel(bin('>', bin('+', name('a'), name('b')), num(1)))).toBeNull()
    expect(conditionToModel(call('has', name('rope')))).toBeNull()
  })

  it('treats empty as no rows', () => {
    expect(conditionToModel(null)).toEqual({ join: 'and', rows: [] })
    expect(modelToCondition({ join: 'and', rows: [] })).toBe('')
  })
})

describe('effects', () => {
  it('round-trips assignments and items', () => {
    const ast: AstNode = {
      type: 'program',
      statements: [
        assign('gold', '-=', num(10)),
        assign('met', '=', bool(true)),
        assign('name', '=', str('Ana')),
        call('give', str('arrow'), num(5)),
        call('take', str('rope')),
      ],
    }
    const rows = effectsToRows(ast)!
    expect(rows).toHaveLength(5)
    expect(rowsToEffects(rows)).toBe('gold -= 10\nmet = true\nname = "Ana"\ngive("arrow", 5)\ntake("rope")')
  })

  it('refuses what the builder cannot show', () => {
    expect(effectsToRows({ type: 'program', statements: [assign('hp', '=', call('min', name('hp'), num(10)))] })).toBeNull()
    expect(effectsToRows({ type: 'program', statements: [assign('hp', '*=', num(2))] })).toBeNull()
    expect(effectsToRows({ type: 'program', statements: [call('give', str('x'), name('n'))] })).toBeNull()
  })
})
