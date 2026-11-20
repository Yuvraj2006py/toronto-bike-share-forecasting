import { createContext, use, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { ApiError, api } from '../api/client'
import type { MapResponse, MetaResponse, StationFeature, StationResponse } from '../api/types'
import { canStep, stepHour } from '../lib/hour'
import {
  readContextCollapsed,
  readSideCollapsed,
  writeContextCollapsed,
  writeSideCollapsed,
} from '../lib/panelPrefs'
import {
  historyHasStation,
  pushStation,
  readStationParam,
  replaceStation,
} from '../lib/urlState'

export type Load<T> =
  | { status: 'loading'; previous: T | null }
  | { status: 'ready'; data: T }
  | { status: 'error'; error: ApiError; previous: T | null }

export type Selection = { stationId: number; origin: 'map' | 'list' | 'url' } | null

export interface MapAppState {
  meta: MetaResponse | null
  map: Load<MapResponse>
  station: Load<StationResponse> | null
  selection: Selection
  clockHour: string | null
  clockLocal: string | null
  listOpen: boolean
  contextCollapsed: boolean
  sideCollapsed: boolean
}

export interface MapAppActions {
  step: (delta: number) => void
  goToHour: (hour: string) => void
  goNow: () => void
  select: (stationId: number | null, origin?: 'map' | 'list' | 'url') => void
  retry: () => void
  setListOpen: (open: boolean) => void
  setContextCollapsed: (collapsed: boolean) => void
  setSideCollapsed: (collapsed: boolean) => void
}

export interface MapAppMeta {
  hour: string | null
  mapData: MapResponse | null
  busiest: StationFeature[]
  canStepBack: boolean
  canStepForward: boolean
  isNow: boolean
  scaleMax: number
}

interface MapAppValue {
  state: MapAppState
  actions: MapAppActions
  meta: MapAppMeta
}

const MapAppContext = createContext<MapAppValue | null>(null)

const BUSIEST_COUNT = 8
const FALLBACK_SCALE_MAX = 10

function toApiError(error: unknown): ApiError {
  return error instanceof ApiError ? error : new ApiError('server', String(error))
}

function isAbort(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError'
}

export function dataOf<T>(load: Load<T> | null): T | null {
  if (load === null) return null
  switch (load.status) {
    case 'ready':
      return load.data
    case 'loading':
    case 'error':
      return load.previous
    default: {
      const unreachable: never = load
      return unreachable
    }
  }
}

export function MapAppProvider({ children }: { children: ReactNode }) {
  const [meta, setMeta] = useState<MetaResponse | null>(null)
  // null asks the API to map the visitor's clock; a string is an explicit demo hour.
  const [request, setRequest] = useState<{ hour: string | null; nonce: number }>({ hour: null, nonce: 0 })
  const [map, setMap] = useState<Load<MapResponse>>({ status: 'loading', previous: null })
  const [selection, setSelection] = useState<Selection>(() => {
    const id = typeof window !== 'undefined' ? readStationParam() : null
    return id === null ? null : { stationId: id, origin: 'url' }
  })
  const [station, setStation] = useState<Load<StationResponse> | null>(null)
  const [clock, setClock] = useState<{ hour: string; local: string | null } | null>(null)
  const [listOpen, setListOpen] = useState(false)
  const [contextCollapsed, setContextCollapsedState] = useState(readContextCollapsed)
  const [sideCollapsed, setSideCollapsedState] = useState(readSideCollapsed)
  const mapRef = useRef<MapResponse | null>(null)
  const selectionRef = useRef(selection)
  const skippingUrlSync = useRef(false)
  selectionRef.current = selection

  useEffect(() => {
    const controller = new AbortController()
    api.meta(controller.signal).then(setMeta).catch(() => {
      // meta only tunes the scale and the window; the map request reports the real error
    })
    return () => controller.abort()
  }, [request.nonce])

  useEffect(() => {
    const controller = new AbortController()
    setMap({ status: 'loading', previous: mapRef.current })
    api
      .map(request.hour, controller.signal)
      .then((data) => {
        mapRef.current = data
        setMap({ status: 'ready', data })
        if (data.demo.from_clock) setClock({ hour: data.context.hour_ts, local: data.demo.clock_local })
      })
      .catch((error: unknown) => {
        if (isAbort(error)) return
        setMap({ status: 'error', error: toApiError(error), previous: mapRef.current })
      })
    return () => controller.abort()
  }, [request])

  const mapData = dataOf(map)
  const hour = mapData?.context.hour_ts ?? null
  const selectedId = selection?.stationId ?? null

  useEffect(() => {
    if (selectedId === null || hour === null) {
      setStation(null)
      return
    }
    const controller = new AbortController()
    setStation((prev) => ({ status: 'loading', previous: dataOf(prev) }))
    api
      .station(selectedId, hour, controller.signal)
      .then((data) => setStation({ status: 'ready', data }))
      .catch((error: unknown) => {
        if (isAbort(error)) return
        setStation({ status: 'error', error: toApiError(error), previous: null })
      })
    return () => controller.abort()
  }, [selectedId, hour])

  useEffect(() => {
    const onPop = () => {
      skippingUrlSync.current = true
      const id = readStationParam()
      setSelection(id === null ? null : { stationId: id, origin: 'url' })
      if (id !== null) {
        setListOpen(false)
        setSideCollapsedState(false)
        writeSideCollapsed(false)
      }
      queuePromise.resolve().then(() => {
        skippingUrlSync.current = false
      })
    }
    window.addEventListener('popstate', onPop)
    if (selection?.origin === 'url' && selection.stationId !== null) {
      replaceStation(selection.stationId)
    }
    return () => window.removeEventListener('popstate', onPop)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const bounds = useMemo(() => (meta ? { min: meta.hour_min, max: meta.hour_max } : null), [meta])

  const goToHour = useCallback((next: string) => {
    setRequest((r) => ({ hour: next, nonce: r.nonce + 1 }))
  }, [])

  const step = useCallback(
    (delta: number) => {
      if (hour === null) return
      if (bounds && !canStep(hour, delta, bounds.min, bounds.max)) return
      goToHour(stepHour(hour, delta))
    },
    [hour, bounds, goToHour],
  )

  const goNow = useCallback(() => {
    setRequest((r) => ({ hour: null, nonce: r.nonce + 1 }))
  }, [])

  const setContextCollapsed = useCallback((collapsed: boolean) => {
    setContextCollapsedState(collapsed)
    writeContextCollapsed(collapsed)
  }, [])

  const setSideCollapsed = useCallback((collapsed: boolean) => {
    setSideCollapsedState(collapsed)
    writeSideCollapsed(collapsed)
  }, [])

  const select = useCallback((stationId: number | null, origin: 'map' | 'list' | 'url' = 'map') => {
    const previous = selectionRef.current?.stationId ?? null
    setSelection(stationId === null ? null : { stationId, origin })
    if (stationId !== null) {
      setListOpen(false)
      setSideCollapsedState(false)
      writeSideCollapsed(false)
    }

    if (skippingUrlSync.current || origin === 'url') return

    if (previous === null && stationId !== null) {
      pushStation(stationId)
    } else if (previous !== null && stationId === null) {
      if (historyHasStation()) history.back()
      else replaceStation(null)
    } else {
      replaceStation(stationId)
    }
  }, [])

  const retry = useCallback(() => {
    setRequest((r) => ({ ...r, nonce: r.nonce + 1 }))
  }, [])

  const busiest = useMemo(() => {
    if (!mapData) return []
    return [...mapData.features.features]
      .sort((a, b) => (b.properties.gbm_pred ?? 0) - (a.properties.gbm_pred ?? 0))
      .slice(0, BUSIEST_COUNT)
  }, [mapData])

  const value = useMemo<MapAppValue>(
    () => ({
      state: {
        meta,
        map,
        station,
        selection,
        clockHour: clock?.hour ?? null,
        clockLocal: clock?.local ?? null,
        listOpen,
        contextCollapsed,
        sideCollapsed,
      },
      actions: {
        step,
        goToHour,
        goNow,
        select,
        retry,
        setListOpen,
        setContextCollapsed,
        setSideCollapsed,
      },
      meta: {
        hour,
        mapData,
        busiest,
        canStepBack: hour !== null && (!bounds || canStep(hour, -1, bounds.min, bounds.max)),
        canStepForward: hour !== null && (!bounds || canStep(hour, 1, bounds.min, bounds.max)),
        isNow: hour !== null && hour === clock?.hour,
        scaleMax: meta?.pred_scale_max ?? FALLBACK_SCALE_MAX,
      },
    }),
    [
      meta,
      map,
      station,
      selection,
      clock,
      listOpen,
      contextCollapsed,
      sideCollapsed,
      step,
      goToHour,
      goNow,
      select,
      retry,
      setContextCollapsed,
      setSideCollapsed,
      hour,
      mapData,
      busiest,
      bounds,
    ],
  )

  return <MapAppContext value={value}>{children}</MapAppContext>
}

export function useMapApp(): MapAppValue {
  const value = use(MapAppContext)
  if (value === null) throw new Error('useMapApp must be used inside <MapAppProvider>')
  return value
}
