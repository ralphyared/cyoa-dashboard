// Syntax highlighting for the expression language and scene text markup.

import { HighlightStyle, StreamLanguage, type StringStream } from '@codemirror/language'
import { tags as t } from '@lezer/highlight'

const KEYWORDS = new Set(['and', 'or', 'not', 'true', 'false'])
const FUNCTIONS = new Set([
  'has', 'count', 'visited', 'visits', 'min', 'max', 'round', 'floor', 'ceil', 'abs', 'give', 'take',
])
const TAG_WORDS = new Set(['if', 'elif', 'else'])

const tokenTable = {
  kw: t.keyword,
  fn: t.function(t.variableName),
  str: t.string,
  num: t.number,
  cmt: t.comment,
  op: t.operator,
  var: t.variableName,
  brace: t.brace,
  tagkw: t.controlKeyword,
  strong: t.strong,
  em: t.emphasis,
  mark: t.processingInstruction,
  style: t.tagName,
  hr: t.contentSeparator,
  esc: t.escape,
  fx: t.special(t.tagName),
}

function exprToken(stream: StringStream, inTag: boolean): string | null {
  if (stream.eatSpace()) return null
  const ch = stream.peek()
  if (ch === undefined) return null
  if (!inTag && ch === '#') {
    stream.skipToEnd()
    return 'cmt'
  }
  if (ch === '"' || ch === "'") {
    stream.next()
    let escaped = false
    while (!stream.eol()) {
      const c = stream.next()
      if (c === ch && !escaped) break
      escaped = c === '\\' && !escaped
    }
    return 'str'
  }
  if (/\d/.test(ch)) {
    stream.match(/^\d+(\.\d+)?/)
    return 'num'
  }
  if (/[A-Za-z_]/.test(ch)) {
    const word = stream.match(/^[A-Za-z_]\w*/) as RegExpMatchArray
    const w = word[0]
    if (KEYWORDS.has(w)) return 'kw'
    if (FUNCTIONS.has(w)) return 'fn'
    return 'var'
  }
  if (stream.match(/^(==|!=|<=|>=|\+=|-=|\*=|\/=|[-+*/%<>=(),;])/)) return 'op'
  stream.next()
  return null
}

export const expressionLanguage = StreamLanguage.define<null>({
  name: 'cyoa-expr',
  startState: () => null,
  token: (stream) => exprToken(stream, false),
  tokenTable,
})

interface MarkupState {
  inTag: boolean
  tagStart: boolean
  bold: boolean
  italic: boolean
}

function textStyle(state: MarkupState): string | null {
  const parts = [state.bold && 'strong', state.italic && 'em'].filter(Boolean)
  return parts.length ? parts.join(' ') : null
}

export const markupLanguage = StreamLanguage.define<MarkupState>({
  name: 'cyoa-markup',
  startState: () => ({ inTag: false, tagStart: false, bold: false, italic: false }),
  copyState: (s) => ({ ...s }),
  token(stream, state) {
    if (state.inTag) {
      if (stream.eat('}')) {
        state.inTag = false
        return 'brace'
      }
      if (state.tagStart) {
        state.tagStart = false
        stream.eatSpace()
        if (stream.match('/if')) return 'tagkw'
        const word = stream.match(/^[a-z]+\b/, false) as RegExpMatchArray | null
        if (word && TAG_WORDS.has(word[0])) {
          stream.match(word[0])
          return 'tagkw'
        }
      }
      return exprToken(stream, true)
    }
    if (stream.sol() && stream.match(/^\s*---\s*$/)) return 'hr'
    if (stream.match(/^\\./)) return 'esc'
    if (stream.eat('{')) {
      state.inTag = true
      state.tagStart = true
      return 'brace'
    }
    if (stream.match('**')) {
      state.bold = !state.bold
      return 'mark'
    }
    if (stream.match(/^\*(?=\S)/) || (state.italic && stream.match('*'))) {
      state.italic = !state.italic
      return 'mark'
    }
    if (stream.match(/^\[\/?(pause|type|glitch)\b[^\]\n]*\]/i)) return 'fx'
    if (stream.match(/^\[\/?([A-Za-z_]+|#[0-9a-fA-F]{6})?\]/)) return 'style'
    if (stream.eatWhile(/[^{\\*[]/)) return textStyle(state)
    stream.next()
    return textStyle(state)
  },
  blankLine(state) {
    state.bold = false
    state.italic = false
  },
  tokenTable,
})

export const highlightStyle = HighlightStyle.define([
  { tag: t.keyword, color: '#c4b5fd' },
  { tag: t.controlKeyword, color: '#c4b5fd', fontWeight: '600' },
  { tag: t.function(t.variableName), color: '#67e8f9' },
  { tag: t.string, color: '#fcd34d' },
  { tag: t.number, color: '#fdba74' },
  { tag: t.comment, color: '#71717a', fontStyle: 'italic' },
  { tag: t.operator, color: '#a1a1aa' },
  { tag: t.variableName, color: '#86efac' },
  { tag: t.brace, color: '#22d3ee', fontWeight: '600' },
  { tag: t.strong, fontWeight: '700', color: '#fafafa' },
  { tag: t.emphasis, fontStyle: 'italic' },
  { tag: t.processingInstruction, color: '#71717a' },
  { tag: t.tagName, color: '#f9a8d4' },
  { tag: t.special(t.tagName), color: '#fbbf24', fontWeight: '600' },
  { tag: t.contentSeparator, color: '#a78bfa', fontWeight: '700' },
  { tag: t.escape, color: '#71717a' },
])
