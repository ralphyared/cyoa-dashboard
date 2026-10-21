import {
  autocompletion,
  closeBrackets,
  closeBracketsKeymap,
  completionKeymap,
  startCompletion,
  type Completion,
  type CompletionContext,
  type CompletionResult,
} from '@codemirror/autocomplete'
import { defaultKeymap, history, historyKeymap } from '@codemirror/commands'
import { syntaxHighlighting } from '@codemirror/language'
import { lintGutter, setDiagnostics, type Diagnostic } from '@codemirror/lint'
import { Compartment, EditorState, type Extension } from '@codemirror/state'
import {
  EditorView,
  keymap,
  placeholder as placeholderExt,
  type ViewUpdate,
} from '@codemirror/view'
import { cx as clsx, useReadOnly } from '../ui'
import { useEffect, useLayoutEffect, useRef } from 'react'
import { useGame } from '@/lib/queries'
import { TYPING_SPEEDS } from '@/lib/typing'
import { useCheck } from '@/lib/useCheck'
import type { CheckMode, CheckResult, GameDetail } from '@/lib/types'
import { expressionLanguage, highlightStyle, markupLanguage } from './languages'

export interface CompletionData {
  variables: { name: string; type: string; label: string }[]
  items: { id: string; name: string }[]
  scenes: { id: string; title: string }[]
}

const FUNCTION_HELP: Record<string, [string, 'item' | 'scene' | 'number']> = {
  has: ['true if carrying the item', 'item'],
  count: ['how many of the item are carried', 'item'],
  visited: ['true if the scene has been entered', 'scene'],
  visits: ['how many times the scene was entered', 'scene'],
  min: ['the smallest value', 'number'],
  max: ['the largest value', 'number'],
  round: ['nearest whole number', 'number'],
  floor: ['round down', 'number'],
  ceil: ['round up', 'number'],
  abs: ['distance from zero', 'number'],
  give: ['add an item (effects only)', 'item'],
  take: ['remove an item (effects only)', 'item'],
}
const EFFECT_ONLY = new Set(['give', 'take'])

function selectCompletionData(game: GameDetail): CompletionData {
  return {
    variables: game.meta.variables.map((v) => ({ name: v.name, type: v.type, label: v.label })),
    items: game.meta.items.map((i) => ({ id: i.id, name: i.name })),
    scenes: game.scenes.map((s) => ({ id: s.id, title: s.title })),
  }
}

function insertCall(name: string, kind: 'item' | 'scene' | 'number') {
  return (view: EditorView, _c: Completion, from: number, to: number) => {
    const text = kind === 'number' ? `${name}()` : `${name}("")`
    const cursor = from + name.length + (kind === 'number' ? 1 : 2)
    view.dispatch({ changes: { from, to, insert: text }, selection: { anchor: cursor } })
    if (kind !== 'number') startCompletion(view)
  }
}

function completionSource(data: { current: CompletionData }, mode: CheckMode) {
  return (ctx: CompletionContext): CompletionResult | null => {
    const line = ctx.state.doc.lineAt(ctx.pos)
    const before = line.text.slice(0, ctx.pos - line.from)

    const quoted = /(has|count|give|take|visited|visits)\(\s*["']([\w]*)$/.exec(before)
    if (quoted) {
      const isScene = quoted[1] === 'visited' || quoted[1] === 'visits'
      const options: Completion[] = isScene
        ? data.current.scenes.map((s) => ({ label: s.id, detail: s.title, type: 'constant' }))
        : data.current.items.map((i) => ({ label: i.id, detail: i.name, type: 'constant' }))
      return { from: ctx.pos - quoted[2].length, options, validFor: /^\w*$/ }
    }

    let inExpression = mode !== 'markup'
    if (mode === 'markup') {
      const open = before.lastIndexOf('{')
      inExpression = open > before.lastIndexOf('}') && before[open - 1] !== '\\'
      if (!inExpression) {
        const style = /\[\/?([a-z_]*)$/.exec(before)
        if (style) {
          const colors = ['red', 'green', 'yellow', 'blue', 'magenta', 'cyan', 'white', 'gray',
            'orange', 'purple', 'gold', 'pink', 'bright_red', 'bright_green', 'bright_yellow',
            'bright_blue', 'bright_magenta', 'bright_cyan', 'bold', 'italic', 'underline', 'dim']
          const effects: Completion[] = before.endsWith('[/')
            ? [{ label: 'type', type: 'function' }, { label: 'glitch', type: 'function' }]
            : [
                { label: 'pause 2', detail: 'wait 2 seconds', type: 'function' },
                { label: 'type', detail: 'type out at the game speed…[/type]', type: 'function' },
                ...TYPING_SPEEDS.map((s) => ({
                  label: `type ${s.level}`,
                  detail: `type out ${s.name}…[/type]`,
                  type: 'function',
                  boost: -1,
                })),
                { label: 'glitch', detail: 'glitch in…[/glitch]', type: 'function' },
              ]
          return {
            from: ctx.pos - style[1].length,
            options: [...effects, ...colors.map((c) => ({ label: c, type: 'keyword' }))],
            validFor: /^[\w ]*$/,
          }
        }
        return null
      }
    }
    if (!inExpression) return null
    const word = ctx.matchBefore(/[A-Za-z_]\w*/)
    if (!word && !ctx.explicit) return null
    const options: Completion[] = [
      ...data.current.variables.map((v) => ({
        label: v.name,
        detail: v.label ? `${v.type} · ${v.label}` : v.type,
        type: 'variable',
        boost: 2,
      })),
      ...Object.entries(FUNCTION_HELP)
        .filter(([name]) => mode === 'effects' || !EFFECT_ONLY.has(name))
        .map(([name, [help, kind]]) => ({
          label: name,
          detail: help,
          type: 'function',
          apply: insertCall(name, kind),
        })),
      ...['and', 'or', 'not', 'true', 'false'].map((k) => ({ label: k, type: 'keyword', boost: -1 })),
    ]
    if (mode === 'markup') {
      options.push(
        { label: 'if', type: 'keyword', apply: 'if ', boost: 1 },
        { label: 'elif', type: 'keyword', apply: 'elif ' },
        { label: 'else', type: 'keyword' },
      )
    }
    return { from: word ? word.from : ctx.pos, options, validFor: /^\w*$/ }
  }
}

const baseTheme = EditorView.theme({
  '&': { color: '#e4e4e7' },
  '.cm-gutters': { display: 'none' },
})

export interface CodeEditorProps {
  value: string
  onChange: (value: string) => void
  mode: CheckMode | 'plain'
  gameId: string
  singleLine?: boolean
  prose?: boolean
  placeholder?: string
  className?: string
  minHeight?: string
  maxHeight?: string
  autoFocus?: boolean
  onResult?: (result: CheckResult) => void
  onBlur?: () => void
  editorRef?: (view: EditorView | null) => void
}

export function CodeEditor({
  value,
  onChange,
  mode,
  gameId,
  singleLine,
  prose,
  placeholder,
  className,
  minHeight,
  maxHeight,
  autoFocus,
  onResult,
  onBlur,
  editorRef,
}: CodeEditorProps) {
  const host = useRef<HTMLDivElement>(null)
  const view = useRef<EditorView | null>(null)
  const onChangeRef = useRef(onChange)
  const onResultRef = useRef(onResult)
  const onBlurRef = useRef(onBlur)
  const { data: completion } = useGame(gameId, selectCompletionData)
  const completionRef = useRef<CompletionData>({ variables: [], items: [], scenes: [] })
  useLayoutEffect(() => {
    onChangeRef.current = onChange
    onResultRef.current = onResult
    onBlurRef.current = onBlur
    if (completion) completionRef.current = completion
  })
  const placeholderCompartment = useRef(new Compartment())
  const readOnly = useReadOnly()

  useEffect(() => {
    if (!host.current) return
    const extensions: Extension[] = [
      EditorState.readOnly.of(readOnly),
      history(),
      closeBrackets(),
      keymap.of([...closeBracketsKeymap, ...defaultKeymap, ...historyKeymap, ...completionKeymap]),
      syntaxHighlighting(highlightStyle),
      baseTheme,
      lintGutter(),
      placeholderCompartment.current.of(placeholder ? placeholderExt(placeholder) : []),
      EditorView.updateListener.of((update: ViewUpdate) => {
        if (update.docChanged) onChangeRef.current(update.state.doc.toString())
        if (update.focusChanged && !update.view.hasFocus) onBlurRef.current?.()
      }),
    ]
    if (mode !== 'plain') {
      extensions.push(
        mode === 'markup' ? markupLanguage : expressionLanguage,
        autocompletion({ override: [completionSource(completionRef, mode)], icons: false }),
      )
    }
    if (mode === 'markup' || mode === 'plain' || mode === 'effects') {
      extensions.push(EditorView.lineWrapping)
    }
    if (singleLine) {
      extensions.push(
        EditorState.transactionFilter.of((tr) => (tr.newDoc.lines > 1 ? [] : tr)),
        keymap.of([{ key: 'Enter', run: () => true }]),
      )
    }
    if (prose) extensions.push(EditorView.editorAttributes.of({ class: 'cm-prose' }))
    extensions.push(
      EditorView.theme({
        '.cm-content': minHeight ? { minHeight } : {},
        '.cm-scroller': maxHeight ? { maxHeight, overflow: 'auto' } : {},
      }),
    )
    const v = new EditorView({
      state: EditorState.create({ doc: value, extensions }),
      parent: host.current,
    })
    view.current = v
    editorRef?.(v)
    if (autoFocus) v.focus()
    return () => {
      editorRef?.(null)
      v.destroy()
      view.current = null
    }
    // The editor is created once per mode; other prop changes are synced below.
  }, [mode, singleLine, prose, readOnly])

  useEffect(() => {
    view.current?.dispatch({
      effects: placeholderCompartment.current.reconfigure(
        placeholder ? placeholderExt(placeholder) : [],
      ),
    })
  }, [placeholder])

  // Sync value changes that came from outside the editor (undo of a rename, reload...).
  useEffect(() => {
    const v = view.current
    if (v && v.state.doc.toString() !== value) {
      v.dispatch({ changes: { from: 0, to: v.state.doc.length, insert: value } })
    }
  }, [value])

  // Live checking against the game's declared variables, items and scenes.
  const check = useCheck(gameId, value, mode)
  useEffect(() => {
    const v = view.current
    const result = check.result
    if (!v || !result || check.source !== v.state.doc.toString()) return
    const len = v.state.doc.length
    const diagnostics: Diagnostic[] = result.errors.map((e) => {
      let from = Math.min(Math.max(0, e.start), len)
      let to = Math.min(Math.max(from, e.end), len)
      if (from === to && len > 0) {
        from = Math.max(0, Math.min(from, len - 1))
        to = from + 1
      }
      return { from, to, severity: 'error', message: e.message }
    })
    v.dispatch(setDiagnostics(v.state, diagnostics))
    onResultRef.current?.(result)
  }, [check.result, check.source])

  return <div ref={host} className={clsx('min-w-0', className)} />
}
