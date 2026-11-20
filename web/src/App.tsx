import { useEffect, useRef } from 'react'
import { ContextCard } from './components/ContextCard'
import { Credits } from './components/Credits'
import { ErrorScreen } from './components/ErrorScreen'
import { MapView } from './components/MapView'
import { BusiestList, StationPanel } from './components/SidePanel'
import { TimeBar } from './components/TimeBar'
import { MapAppProvider, useMapApp } from './state/MapAppContext'

function isTyping(target: EventTarget | null): boolean {
  return target instanceof HTMLElement && (target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName))
}

function useKeyboard() {
  const { state, actions } = useMapApp()
  const hasSelection = state.selection !== null
  const listOpen = state.listOpen
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (isTyping(event.target) || event.metaKey || event.ctrlKey || event.altKey) return
      if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
        // Leave arrows for MapLibre pan unless the time bar owns focus.
        if (!(event.target instanceof Element) || !event.target.closest('.timebar')) return
        event.preventDefault()
        actions.step(event.key === 'ArrowLeft' ? -1 : 1)
      } else if (event.key === '[' || event.key === ']') {
        event.preventDefault()
        actions.step(event.key === '[' ? -1 : 1)
      } else if (event.key === 'Escape') {
        if (hasSelection) actions.select(null)
        else if (listOpen) actions.setListOpen(false)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [actions, hasSelection, listOpen])
}

// Publishes the dock height so the side panel and map controls stop above it.
function useDockHeight() {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const dock = ref.current
    if (!dock) return
    const observer = new ResizeObserver(([entry]) => {
      if (entry) document.documentElement.style.setProperty('--dock-h', `${Math.ceil(entry.contentRect.height)}px`)
    })
    observer.observe(dock)
    return () => observer.disconnect()
  }, [])
  return ref
}

function Shell() {
  const { state, meta } = useMapApp()
  const dockRef = useDockHeight()
  useKeyboard()

  useEffect(() => {
    document.documentElement.dataset.contextCollapsed = state.contextCollapsed ? '1' : '0'
    document.documentElement.dataset.sideCollapsed = state.sideCollapsed ? '1' : '0'
  }, [state.contextCollapsed, state.sideCollapsed])

  if (state.map.status === 'error' && meta.mapData === null) {
    return <ErrorScreen error={state.map.error} />
  }

  return (
    <div className="app">
      <MapView />
      <div className="overlay">
        <ContextCard />
        {state.selection ? <StationPanel /> : <BusiestList />}
        <div className="dock" ref={dockRef}>
          <TimeBar />
          <Credits />
        </div>
      </div>
      {state.map.status === 'error' && (
        <p className="toast" role="status">Couldn't load that hour: {state.map.error.message}</p>
      )}
    </div>
  )
}

export default function App() {
  return (
    <MapAppProvider>
      <Shell />
    </MapAppProvider>
  )
}
