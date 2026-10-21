import { useQueryClient } from '@tanstack/react-query'
import { Trash2, Wand2 } from 'lucide-react'
import { useState } from 'react'
import { useNavigate } from 'react-router'
import { CodeEditor } from '@/components/editor/CodeEditor'
import { ScenePicker } from '@/components/ScenePicker'
import { Button, Checkbox, Field, Input, Select, Textarea, cx, useReadOnly } from '@/components/ui'
import { api } from '@/lib/api'
import { useAccess, useGameActions, useMeta } from '@/lib/queries'
import type { Settings } from '@/lib/types'
import { TYPING_SPEEDS } from '@/lib/typing'
import { useWorkspace } from './context'
import { ConfirmDelete, PageShell } from './shared'

const ACCENTS: [string, string][] = [
  ['cyan', '#22d3ee'], ['green', '#4ade80'], ['yellow', '#facc15'], ['magenta', '#e879f9'],
  ['red', '#f87171'], ['blue', '#60a5fa'], ['white', '#f4f4f5'], ['dark_orange', '#fb923c'],
]

export function SettingsPage() {
  const { gameId } = useWorkspace()
  const meta = useMeta(gameId)
  const actions = useGameActions(gameId)
  const qc = useQueryClient()
  const navigate = useNavigate()
  const [deleting, setDeleting] = useState(false)
  const readOnly = useReadOnly()
  const isOwner = useAccess(gameId) === 'owner'
  if (!meta) return null
  const settings = meta.settings
  const setSettings = (changes: Partial<Settings>) => actions.updateMeta({ settings: { ...settings, ...changes } })

  function generateStatus() {
    const numbers = meta!.variables.filter((v) => v.type === 'number')
    const parts: string[] = []
    const used = new Set<string>()
    for (const v of numbers) {
      if (used.has(v.name)) continue
      const maxVar = typeof v.max === 'string' ? v.max : null
      if (maxVar) used.add(maxVar)
      parts.push(`${v.label || v.name} {${v.name}}${maxVar ? `/{${maxVar}}` : ''}`)
      used.add(v.name)
    }
    setSettings({ status_format: parts.join(' │ ') })
  }

  async function deleteGame() {
    await actions.reload()
    await api.deleteGame(gameId)
    await qc.invalidateQueries({ queryKey: ['games'] })
    navigate('/')
  }

  return (
    <PageShell title="Settings">
      <section className="grid gap-4 sm:grid-cols-2">
        <Field label="Title">
          <Input value={meta.title} onChange={(e) => actions.updateMeta({ title: e.target.value })} />
        </Field>
        <Field label="Author">
          <Input value={meta.author} onChange={(e) => actions.updateMeta({ author: e.target.value })} />
        </Field>
        <Field label="Short description" hint="Shown on the title screen" className="sm:col-span-2">
          <Input value={meta.description} onChange={(e) => actions.updateMeta({ description: e.target.value })} />
        </Field>
        <Field label="Version" hint="Saves remember which version they came from">
          <Input value={meta.version} onChange={(e) => actions.updateMeta({ version: e.target.value })} />
        </Field>
        <Field label="Start scene" hint="Where a new game begins">
          <ScenePicker gameId={gameId} value={meta.start_scene} onChange={(start_scene) => actions.updateMeta({ start_scene })} />
        </Field>
      </section>

      <section className="flex flex-col gap-4 border-t border-surface-700 pt-5">
        <h2 className="text-sm font-semibold text-zinc-200">Look &amp; feel</h2>
        <Field label="Accent color" hint="Used for choice numbers, the status bar and borders">
          <div className="flex flex-wrap gap-2">
            {ACCENTS.map(([name, color]) => (
              <button
                key={name}
                type="button"
                disabled={readOnly}
                onClick={() => setSettings({ accent_color: name })}
                className={cx(
                  'flex items-center gap-1.5 rounded-md border px-2 py-1 text-xs disabled:cursor-default',
                  settings.accent_color === name ? 'border-zinc-300 text-zinc-100' : 'border-surface-700 text-zinc-400 hover:border-surface-600',
                )}
              >
                <span className="size-3 rounded-full" style={{ background: color }} />
                {name.replace('_', ' ')}
              </button>
            ))}
          </div>
        </Field>
        <Field
          label={
            <div className="flex items-center justify-between">
              <span>Status bar</span>
              {!readOnly && (
                <Button size="xs" variant="ghost" icon={<Wand2 className="size-3" />} onClick={generateStatus} disabled={meta.variables.length === 0}>
                  Generate from variables
                </Button>
              )}
            </div>
          }
          hint="Shown at the top of every scene. Use {variable} for values and [red]…[/red] for color. Leave empty for no status bar."
        >
          <CodeEditor
            gameId={gameId}
            mode="markup"
            singleLine
            value={settings.status_format}
            onChange={(status_format) => setSettings({ status_format })}
            placeholder="e.g. HP {hp}/{max_hp} │ Gold {gold}"
          />
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Text width" hint="Columns; the player's terminal may be narrower">
            <Select value={settings.text_width} onChange={(e) => setSettings({ text_width: Number(e.target.value) })}>
              {[60, 70, 80, 90, 100, 120].map((w) => (
                <option key={w} value={w}>
                  {w} columns
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Typing speed" hint="For the typewriter effect and [type] passages. Players can pick their own.">
            <Select value={settings.typing_speed ?? 6} onChange={(e) => setSettings({ typing_speed: Number(e.target.value) })}>
              {TYPING_SPEEDS.map((s) => (
                <option key={s.level} value={s.level}>
                  {s.level} · {s.name} ({s.cps} letters a second)
                </option>
              ))}
            </Select>
          </Field>
          <div className="flex flex-col justify-center gap-2 sm:col-span-2">
            <Checkbox
              checked={settings.typewriter}
              onChange={(typewriter) => setSettings({ typewriter })}
              label="Type out all text (typewriter effect) by default (players can change it)"
            />
            <Checkbox
              checked={settings.show_scene_titles}
              onChange={(show_scene_titles) => setSettings({ show_scene_titles })}
              label="Show scene titles to players (next to the chapter)"
            />
          </div>
        </div>
        <Field label="Title screen ASCII art" hint="Centered above the title. Leave empty for a simple framed title.">
          <Textarea
            value={settings.title_art}
            onChange={(e) => setSettings({ title_art: e.target.value })}
            rows={Math.min(14, Math.max(4, settings.title_art.split('\n').length + 1))}
            spellCheck={false}
            wrap="off"
            className="font-mono text-xs leading-tight whitespace-pre"
          />
        </Field>
        <Field label="Intro" hint="Shown after “New Game”, before the first scene. Supports the same markup as scenes, including --- page breaks.">
          <CodeEditor
            gameId={gameId}
            mode="markup"
            prose
            value={settings.intro}
            onChange={(intro) => setSettings({ intro })}
            minHeight="5rem"
          />
        </Field>
      </section>

      {isOwner && (
        <section className="flex items-center justify-between gap-4 rounded-lg border border-red-500/30 p-4">
          <div>
            <div className="text-sm font-medium text-zinc-200">Delete this game</div>
            <div className="text-xs text-zinc-500">Moves it to the trash. You can restore it from there.</div>
          </div>
          <Button variant="danger" icon={<Trash2 className="size-3.5" />} onClick={() => setDeleting(true)}>
            Delete game
          </Button>
        </section>
      )}
      <ConfirmDelete
        open={deleting}
        onOpenChange={setDeleting}
        title={`Move “${meta.title}” to the trash?`}
        onConfirm={() => void deleteGame()}
      />
    </PageShell>
  )
}
