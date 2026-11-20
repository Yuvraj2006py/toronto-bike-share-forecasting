// Demo hours are naive Toronto wall-clock strings ("2024-09-23T08:00:00"). They are parsed as UTC
// purely for arithmetic so the browser's own timezone can never shift them.

const WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'] as const
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'] as const
const HOUR_MS = 3_600_000

function toWall(iso: string): Date {
  const trimmed = iso.length === 16 ? `${iso}:00` : iso.slice(0, 19)
  return new Date(`${trimmed}Z`)
}

function fromWall(date: Date): string {
  return date.toISOString().slice(0, 19)
}

function clock12(hours: number, minutes: number): string {
  const suffix = hours < 12 ? 'AM' : 'PM'
  const h = hours % 12 === 0 ? 12 : hours % 12
  return `${h}:${String(minutes).padStart(2, '0')} ${suffix}`
}

export function stepHour(iso: string, delta: number): string {
  return fromWall(new Date(toWall(iso).getTime() + delta * HOUR_MS))
}

export function canStep(iso: string, delta: number, min: string, max: string): boolean {
  const next = toWall(stepHour(iso, delta)).getTime()
  return next >= toWall(min).getTime() && next <= toWall(max).getTime()
}

export function dayHours(iso: string): string[] {
  const start = toWall(`${iso.slice(0, 10)}T00:00:00`).getTime()
  return Array.from({ length: 24 }, (_, i) => fromWall(new Date(start + i * HOUR_MS)))
}

export function isWithin(iso: string, min: string, max: string): boolean {
  const t = toWall(iso).getTime()
  return t >= toWall(min).getTime() && t <= toWall(max).getTime()
}

export function formatHour(iso: string): string {
  const d = toWall(iso)
  return `${WEEKDAYS[d.getUTCDay()]} ${clock12(d.getUTCHours(), d.getUTCMinutes())}`
}

export function formatHourShort(iso: string): string {
  const h = toWall(iso).getUTCHours()
  if (h === 0) return '12a'
  if (h === 12) return '12p'
  return h < 12 ? `${h}a` : `${h - 12}p`
}

export function formatDay(iso: string): string {
  const d = toWall(iso)
  return `${MONTHS[d.getUTCMonth()]} ${d.getUTCDate()}, ${d.getUTCFullYear()}`
}

export const formatClock = formatHour
