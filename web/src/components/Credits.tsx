import { useMapApp } from '../state/MapAppContext'

const FALLBACK = [
  { label: 'Ridership: City of Toronto, Open Government Licence – Toronto', url: 'https://open.toronto.ca/open-data-licence/' },
  { label: 'Weather: Open-Meteo (observed, historical)', url: 'https://open-meteo.com/' },
  { label: 'Stations: Bike Share Toronto GBFS', url: 'https://tor.publicbikesystem.net/ube/gbfs/v1/' },
  { label: 'Basemap: OpenFreeMap, © OpenStreetMap contributors', url: 'https://openfreemap.org/' },
]

export function Credits() {
  const { state } = useMapApp()
  const items = state.meta?.attribution ?? FALLBACK
  const missing = state.meta?.stations_missing_geo ?? 0
  return (
    <footer className="credits">
      <span>Weather is what was observed in that 2024 hour, not today's forecast.</span>
      {missing > 0 && <span>{missing} retired stations have no location and are left off.</span>}
      {items.map((a) => (
        <a key={a.url} className="link" href={a.url} target="_blank" rel="noreferrer">{a.label}</a>
      ))}
    </footer>
  )
}
