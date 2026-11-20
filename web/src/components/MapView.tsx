import { Map as MlMap, NavigationControl, setWorkerUrl } from 'maplibre-gl'
import type { ErrorEvent, ExpressionSpecification, GeoJSONSource, MapLayerMouseEvent, MapMouseEvent } from 'maplibre-gl'
import maplibreWorkerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url'
import 'maplibre-gl/dist/maplibre-gl.css'
import { useEffect, useRef, useState } from 'react'
import type { StationCollection } from '../api/types'
import { circleColorExpression, circleRadiusExpression } from '../lib/colors'
import { useMapApp } from '../state/MapAppContext'

// Explicit worker URL: nginx must serve .mjs as application/javascript (see nginx.conf).
setWorkerUrl(maplibreWorkerUrl)

const BASEMAP_URL = 'https://tiles.openfreemap.org/styles/dark'
const TORONTO_CENTER: [number, number] = [-79.392, 43.665]
const SOURCE_ID = 'stations'
const LAYER_ID = 'stations-circle'
const SELECTED_LAYER_ID = 'stations-selected'
const EMPTY: StationCollection = { type: 'FeatureCollection', features: [] }

function firstSymbolLayerId(map: MlMap): string | undefined {
  return map.getStyle().layers?.find((layer) => layer.type === 'symbol')?.id
}

function stationRadius(scaleMax: number): ExpressionSpecification {
  return [
    '*',
    circleRadiusExpression(scaleMax),
    ['case', ['boolean', ['feature-state', 'hover'], false], 1.35, 1],
  ]
}

function ensureStationLayers(map: MlMap, scaleMax: number, data: StationCollection | null) {
  if (!map.getSource(SOURCE_ID)) {
    map.addSource(SOURCE_ID, { type: 'geojson', data: data ?? EMPTY, promoteId: 'station_id' })
  } else if (data) {
    ;(map.getSource(SOURCE_ID) as GeoJSONSource).setData(data)
  }

  if (!map.getLayer(LAYER_ID)) {
    const layer = {
      id: LAYER_ID,
      type: 'circle' as const,
      source: SOURCE_ID,
      paint: {
        'circle-color': circleColorExpression(scaleMax),
        'circle-radius': stationRadius(scaleMax),
        'circle-opacity': 0.92,
        'circle-stroke-color': 'rgba(15,15,15,0.85)',
        'circle-stroke-width': ['interpolate', ['linear'], ['zoom'], 10, 0.4, 14, 1] as ExpressionSpecification,
        'circle-radius-transition': { duration: 160 },
        'circle-color-transition': { duration: 260 },
      },
    }
    const beforeId = firstSymbolLayerId(map)
    try {
      map.addLayer(layer, beforeId)
    } catch {
      map.addLayer(layer)
    }
  }

  if (!map.getLayer(SELECTED_LAYER_ID)) {
    map.addLayer({
      id: SELECTED_LAYER_ID,
      type: 'circle',
      source: SOURCE_ID,
      filter: ['==', ['get', 'station_id'], -1],
      paint: {
        'circle-color': 'rgba(0,0,0,0)',
        'circle-radius': ['+', circleRadiusExpression(scaleMax), 5],
        'circle-stroke-color': '#dafa9c',
        'circle-stroke-width': 2.5,
      },
    })
  }
}

export function MapView() {
  const { state, actions, meta } = useMapApp()
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<MlMap | null>(null)
  const hoverRef = useRef<number | null>(null)
  const selectRef = useRef(actions.select)
  const scaleRef = useRef(meta.scaleMax)
  const featuresRef = useRef<StationCollection | null>(null)
  const [ready, setReady] = useState(false)
  selectRef.current = actions.select
  scaleRef.current = meta.scaleMax
  featuresRef.current = meta.mapData?.features ?? featuresRef.current

  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    let cancelled = false
    let settled = false
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const map = new MlMap({
      container,
      style: BASEMAP_URL,
      center: TORONTO_CENTER,
      zoom: window.innerWidth < 640 ? 10.6 : 11.6,
      minZoom: 9,
      maxZoom: 17,
      attributionControl: { compact: true },
      fadeDuration: reduceMotion ? 0 : 200,
      cooperativeGestures: false,
    })
    mapRef.current = map
    Object.assign(window, { __map: map })

    const mountStations = () => {
      if (cancelled) return
      try {
        ensureStationLayers(map, scaleRef.current, featuresRef.current)
        map.resize()
        if (!settled) {
          settled = true
          setReady(true)
        }
      } catch (error) {
        console.error('Failed to add station layers', error)
      }
    }

    // style.load can fire more than once (and sometimes during construction). Always re-ensure
    // our layers — a style swap wipes custom layers.
    map.on('style.load', mountStations)
    map.on('load', mountStations)
    const poll = window.setInterval(() => {
      if (cancelled || !map.isStyleLoaded()) return
      mountStations()
      if (map.getLayer(LAYER_ID)) window.clearInterval(poll)
    }, 150)
    window.setTimeout(() => window.clearInterval(poll), 20_000)

    map.addControl(new NavigationControl({ showCompass: false }), 'bottom-right')
    map.on('error', (event: ErrorEvent) => {
      if (import.meta.env.DEV) console.warn('map error', event.error)
    })

    const setHover = (id: number | null) => {
      if (!map.getSource(SOURCE_ID)) return
      if (hoverRef.current !== null) {
        map.setFeatureState({ source: SOURCE_ID, id: hoverRef.current }, { hover: false })
      }
      hoverRef.current = id
      if (id !== null) map.setFeatureState({ source: SOURCE_ID, id }, { hover: true })
    }
    map.on('mousemove', LAYER_ID, (event: MapLayerMouseEvent) => {
      const id = event.features?.[0]?.id
      map.getCanvas().style.cursor = 'pointer'
      setHover(typeof id === 'number' ? id : null)
    })
    map.on('mouseleave', LAYER_ID, () => {
      map.getCanvas().style.cursor = ''
      setHover(null)
    })
    map.on('click', (event: MapMouseEvent) => {
      if (!map.getLayer(LAYER_ID)) return
      const hit = map.queryRenderedFeatures(event.point, { layers: [LAYER_ID] })[0]
      const id = hit?.properties?.station_id
      selectRef.current(typeof id === 'number' ? id : null, 'map')
    })

    return () => {
      cancelled = true
      window.clearInterval(poll)
      map.remove()
      mapRef.current = null
      setReady(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const features = meta.mapData?.features ?? null
  useEffect(() => {
    featuresRef.current = features
    const map = mapRef.current
    if (!ready || !map || !features || !map.getSource(SOURCE_ID)) return
    ;(map.getSource(SOURCE_ID) as GeoJSONSource).setData(features)
  }, [ready, features])

  useEffect(() => {
    const map = mapRef.current
    if (!ready || !map || !map.getLayer(LAYER_ID)) return
    map.setPaintProperty(LAYER_ID, 'circle-color', circleColorExpression(meta.scaleMax))
    map.setPaintProperty(LAYER_ID, 'circle-radius', stationRadius(meta.scaleMax))
    if (map.getLayer(SELECTED_LAYER_ID)) {
      map.setPaintProperty(SELECTED_LAYER_ID, 'circle-radius', ['+', circleRadiusExpression(meta.scaleMax), 5])
    }
  }, [ready, meta.scaleMax])

  const selection = state.selection
  useEffect(() => {
    const map = mapRef.current
    if (!ready || !map || !map.getLayer(SELECTED_LAYER_ID)) return
    map.setFilter(SELECTED_LAYER_ID, ['==', ['get', 'station_id'], selection?.stationId ?? -1])
    if (selection?.origin !== 'list' || !features) return
    const feature = features.features.find((f) => f.properties.station_id === selection.stationId)
    if (!feature) return
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const sideCollapsed = document.documentElement.dataset.sideCollapsed === '1'
    const contextCollapsed = document.documentElement.dataset.contextCollapsed === '1'
    map.flyTo({
      center: feature.geometry.coordinates,
      zoom: Math.max(map.getZoom(), 13.5),
      duration: reduceMotion ? 0 : 900,
      padding: window.innerWidth < 640
        ? { top: 0, bottom: window.innerHeight * 0.45, left: 0, right: 0 }
        : {
            top: 0,
            bottom: 0,
            left: contextCollapsed ? 48 : 400,
            right: sideCollapsed ? 48 : 380,
          },
    })
  }, [ready, selection, features])

  const loading = state.map.status === 'loading'
  return (
    <div
      ref={containerRef}
      className="map"
      data-loading={loading || undefined}
      role="region"
      aria-label="Map of Toronto bike share stations coloured by predicted departures in the next hour. The busiest stations are listed in the side panel."
    />
  )
}
