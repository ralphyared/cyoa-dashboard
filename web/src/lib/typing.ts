// Mirrors engine/src/cyoa/typing_speed.py.
export const TYPING_SPEEDS: { level: number; name: string; cps: number }[] = [
  { level: 1, name: 'very slow', cps: 10 },
  { level: 2, name: 'slow', cps: 18 },
  { level: 3, name: 'unhurried', cps: 28 },
  { level: 4, name: 'relaxed', cps: 40 },
  { level: 5, name: 'steady', cps: 60 },
  { level: 6, name: 'normal', cps: 80 },
  { level: 7, name: 'brisk', cps: 120 },
  { level: 8, name: 'fast', cps: 200 },
  { level: 9, name: 'very fast', cps: 350 },
]
