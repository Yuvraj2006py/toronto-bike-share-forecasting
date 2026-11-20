/** Sync selected station with the address bar so Back closes the panel. */

export type StationHistoryState = { stationId: number | null }

export function readStationParam(search = window.location.search): number | null {
  const raw = new URLSearchParams(search).get('station')
  if (raw === null || raw === '') return null
  const id = Number(raw)
  return Number.isFinite(id) && id > 0 ? id : null
}

export function stationUrl(stationId: number | null): string {
  const url = new URL(window.location.href)
  if (stationId === null) url.searchParams.delete('station')
  else url.searchParams.set('station', String(stationId))
  return `${url.pathname}${url.search}${url.hash}`
}

export function pushStation(stationId: number): void {
  history.pushState({ stationId } satisfies StationHistoryState, '', stationUrl(stationId))
}

export function replaceStation(stationId: number | null): void {
  history.replaceState({ stationId } satisfies StationHistoryState, '', stationUrl(stationId))
}

export function historyHasStation(): boolean {
  const state = history.state
  return Boolean(state && typeof state === 'object' && 'stationId' in state && state.stationId != null)
}
