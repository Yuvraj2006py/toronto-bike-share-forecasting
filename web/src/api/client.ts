import type { MapResponse, MetaResponse, StationResponse } from './types'

export type ApiErrorKind = 'not-prepared' | 'not-found' | 'network' | 'server'

export class ApiError extends Error {
  readonly kind: ApiErrorKind
  readonly status: number | null

  constructor(kind: ApiErrorKind, message: string, status: number | null = null) {
    super(message)
    this.name = 'ApiError'
    this.kind = kind
    this.status = status
  }
}

function kindForStatus(status: number): ApiErrorKind {
  if (status === 503) return 'not-prepared'
  if (status === 404) return 'not-found'
  return 'server'
}

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  let response: Response
  try {
    response = await fetch(path, { signal, headers: { Accept: 'application/json' } })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new ApiError('network', 'The prediction service could not be reached.')
  }
  if (!response.ok) {
    let detail = response.statusText
    try {
      const body = (await response.json()) as { detail?: unknown }
      if (typeof body.detail === 'string') detail = body.detail
    } catch {
      // body was not JSON; keep the status text
    }
    throw new ApiError(kindForStatus(response.status), detail, response.status)
  }
  return (await response.json()) as T
}

function withHour(path: string, hour: string | null): string {
  return hour ? `${path}?hour=${encodeURIComponent(hour)}` : path
}

export const api = {
  meta: (signal?: AbortSignal) => getJson<MetaResponse>('/api/meta', signal),
  map: (hour: string | null, signal?: AbortSignal) =>
    getJson<MapResponse>(withHour('/api/map', hour), signal),
  station: (stationId: number, hour: string, signal?: AbortSignal) =>
    getJson<StationResponse>(withHour(`/api/station/${stationId}`, hour), signal),
}
