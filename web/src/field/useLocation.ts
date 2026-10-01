import { useEffect, useState } from 'react'
import type { LatLon } from '../types'

export type LocationState =
  | { status: 'pending' }
  | { status: 'ok'; position: LatLon; accuracyM: number }
  | { status: 'unavailable'; reason: string }

/** Watches the device location. Falls back gracefully when permission is denied or GPS is missing. */
export function useDeviceLocation(): LocationState {
  const [state, setState] = useState<LocationState>(() =>
    'geolocation' in navigator ? { status: 'pending' } : { status: 'unavailable', reason: 'This device has no location service' },
  )

  useEffect(() => {
    if (!('geolocation' in navigator)) return
    const id = navigator.geolocation.watchPosition(
      (pos) => setState({ status: 'ok', position: [pos.coords.latitude, pos.coords.longitude], accuracyM: pos.coords.accuracy }),
      (err) =>
        setState({
          status: 'unavailable',
          reason: err.code === err.PERMISSION_DENIED ? 'Location permission was not granted' : 'Location is not available',
        }),
      { enableHighAccuracy: true, maximumAge: 5000, timeout: 15000 },
    )
    return () => navigator.geolocation.clearWatch(id)
  }, [])

  return state
}
