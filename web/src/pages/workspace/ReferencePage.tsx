import type { ReactNode } from 'react'
import { useReference } from '@/lib/queries'
import { PageShell } from './shared'

function Code({ children }: { children: ReactNode }) {
  return <code className="rounded bg-surface-800 px-1 py-0.5 font-mono text-[0.85em] text-accent-300">{children}</code>
}

function Block({ children }: { children: string }) {
  return (
    <pre className="overflow-x-auto rounded-md border border-surface-700 bg-surface-900 px-3 py-2 font-mono text-xs leading-relaxed text-zinc-300">
      {children}
    </pre>
  )
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-2.5 text-sm leading-relaxed text-zinc-300">
      <h2 className="text-base font-semibold text-zinc-100">{title}</h2>
      {children}
    </section>
  )
}

export function ReferencePage() {
  const reference = useReference().data
  return (
    <PageShell title="Help & reference" description="Everything you can write in scenes, conditions and effects.">
      <Section title="Scene text">
        <p>
          Write plain prose. Blank lines separate paragraphs; text wraps to the player's terminal
          automatically. On top of that:
        </p>
        <Block>{`You have {gold} gold coins.               ← shows a variable (any expression works: {gold * 2})

{if hp < 3}You can barely stand.{else}You feel fine.{/if}

{if has("lantern")}
The lantern lights the way.                ← tags alone on their line leave no blank lines
{elif visited("cave")}
You remember the way from last time.
{/if}

**bold**, *italic*, [red]colored text[/red], [bold]…[/bold], [dim]…[/dim]
---                                        ← a line with just --- = "press Enter to continue"
\\{ \\* \\[                                   ← a backslash shows the next character literally`}</Block>
        <p>
          Colors: {reference?.colors.join(', ')}, or any <Code>#rrggbb</Code>. Styles: {reference?.styles.join(', ')}.
          Close with <Code>[/red]</Code> or just <Code>[/]</Code>.
        </p>
      </Section>

      <Section title="Conditions">
        <p>
          Used on choices (only available if…), in rules, and in <Code>{'{if …}'}</Code> text. A condition must
          be true or false:
        </p>
        <Block>{`hp > 0
gold >= 10 and has("rope")
not met_wizard or visits("tavern") >= 3
class == "mage"
count("arrow") >= 2`}</Block>
        <p>
          Compare with <Code>==</Code> <Code>!=</Code> <Code>&lt;</Code> <Code>&lt;=</Code> <Code>&gt;</Code> <Code>&gt;=</Code>, combine with{' '}
          <Code>and</Code>, <Code>or</Code>, <Code>not</Code> and parentheses. Do math with <Code>+ - * / %</Code>. Text goes in
          quotes. A choice whose condition is false is hidden, or shown locked with a hint like
          “[Requires: Gold ≥ 10]” (you can write your own hint).
        </p>
      </Section>

      <Section title="Effects">
        <p>One per line. Used on choices (when chosen), on scenes (when the player arrives) and in rules:</p>
        <Block>{`gold -= 10
hp += 5
hp = max_hp
met_wizard = true
name = "Ana"
give("rope")
give("arrow", 5)
take("arrow")`}</Block>
        <p>
          Numbers with a minimum/maximum (Variables page) are kept inside their limits automatically,
          so <Code>hp += 50</Code> never goes past <Code>max_hp</Code>.
        </p>
      </Section>

      <Section title="Functions">
        <table className="w-full text-left text-sm">
          <tbody className="divide-y divide-surface-800">
            {reference?.functions.map((f) => (
              <tr key={f.name}>
                <td className="py-1.5 pr-4 font-mono text-accent-300">{f.name}</td>
                <td className="py-1.5 text-zinc-400">{f.help}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Section>

      <Section title="How a turn works">
        <ol className="list-decimal space-y-1 pl-5">
          <li>The player picks a choice: its effects apply.</li>
          <li>Rules are checked; a rule that just became true fires (and may send the player elsewhere).</li>
          <li>The player enters the next scene: the visit counts, its arrival effects apply, rules are checked again.</li>
          <li>The scene's text is shown (with the current values), then the available choices.</li>
        </ol>
        <p>
          Scenes marked as an ending show an end screen (“YOU DIED” / “THE END”) and let the player
          load a save or start over. The game autosaves at every scene; players also have 5 save slots.
        </p>
      </Section>

      <Section title="Playtesting">
        <p>
          The Playtest panel runs the real terminal player. “Play from here” starts at the scene you're
          editing. Change variables and items in the panel's Game state section; the game restarts
          in place with the new values. After editing, press <b>Reload</b> to see your changes without
          losing your place. In the terminal you can also type <Code>:goto scene_id</Code>,{' '}
          <Code>:set gold 50</Code>, <Code>:give rope</Code> or <Code>:vars</Code>.
        </p>
      </Section>

      <Section title="Sharing your game">
        <p>
          Use <b>Export → Ready-to-play game</b> and pick your players' system. Windows players get a
          single <Code>.exe</Code> named after your story; they double-click it and play. Mac players get
          a zip with the game and its player (Apple only runs signed programs, so the player can't be
          changed to carry the story inside it). Linux players get a single program. Exporting only
          works when the game has no errors.
        </p>
        <p>
          Players' saves are kept per story on their computer, so different games never mix their saves.
          <b> Project backup</b> keeps everything, including your private notes, so you can import it
          into another dashboard. <b>Game file only</b> is the bare story file, for anyone who already has
          the player (<Code>cyoa-play your_game.cyoa.json</Code>).
        </p>
      </Section>
    </PageShell>
  )
}
