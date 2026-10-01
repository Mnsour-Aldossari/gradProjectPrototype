import { useCallback, useEffect, useReducer, useRef } from 'react'
import { liveUrl } from './api'
import type { Detection, LatLon, Mission, Telemetry } from './types'

const TRACE_LENGTH = 300 // ~30 s of sensor samples at the live event rate

export interface Alert {
  detection: Detection
  receivedAt: number
}

export interface LiveState {
  connection: 'connecting' | 'open' | 'closed'
  mission: Mission | null
  detections: Record<number, Detection>
  track: LatLon[]
  telemetry: Telemetry | null
  trace: { md: number[]; gpr: number[] }
  alerts: Alert[] // newest first, only those raised while this page is open
}

type Event =
  | { type: 'snapshot'; mission: Mission; detections: Detection[]; track: LatLon[]; last_telemetry: Telemetry | null }
  | ({ type: 'telemetry' } & Telemetry)
  | { type: 'mission'; status: Mission['status']; progress: number; battery_pct: number | null; error: string | null }
  | { type: 'detection_created' | 'detection_updated'; detection: Detection }
  | { type: 'alert'; detection: Detection }
  | { type: 'detection_removed'; id: number }

type Action = Event | { type: 'connection'; value: LiveState['connection'] } | { type: 'local_update'; detection: Detection }

const initial: LiveState = {
  connection: 'connecting',
  mission: null,
  detections: {},
  track: [],
  telemetry: null,
  trace: { md: [], gpr: [] },
  alerts: [],
}

function push(values: number[], value: number | null | undefined): number[] {
  if (value === null || value === undefined) return values
  const next = values.length >= TRACE_LENGTH ? values.slice(1) : values.slice()
  next.push(value)
  return next
}

function reducer(state: LiveState, action: Action): LiveState {
  switch (action.type) {
    case 'connection':
      return { ...state, connection: action.value }
    case 'snapshot':
      return {
        ...state,
        mission: action.mission,
        detections: Object.fromEntries(action.detections.map((d) => [d.id, d])),
        track: action.track,
        telemetry: action.last_telemetry,
      }
    case 'telemetry': {
      const { type: _type, ...telemetry } = action
      return {
        ...state,
        telemetry,
        track: [...state.track, [telemetry.lat, telemetry.lon]],
        trace: { md: push(state.trace.md, telemetry.md), gpr: push(state.trace.gpr, telemetry.gpr) },
        mission:
          state.mission && telemetry.progress !== undefined
            ? { ...state.mission, progress: telemetry.progress, battery_pct: telemetry.battery_pct }
            : state.mission,
      }
    }
    case 'mission':
      return state.mission
        ? {
            ...state,
            mission: {
              ...state.mission,
              status: action.status,
              progress: action.progress,
              battery_pct: action.battery_pct,
              error: action.error,
            },
          }
        : state
    case 'detection_created':
    case 'detection_updated':
    case 'local_update':
      return { ...state, detections: { ...state.detections, [action.detection.id]: action.detection } }
    case 'alert':
      return {
        ...state,
        detections: { ...state.detections, [action.detection.id]: action.detection },
        alerts: [{ detection: action.detection, receivedAt: Date.now() }, ...state.alerts],
      }
    case 'detection_removed': {
      const { [action.id]: _removed, ...rest } = state.detections
      return { ...state, detections: rest }
    }
  }
}

export function useMissionLive(missionId: number) {
  const [state, dispatch] = useReducer(reducer, initial)
  const retry = useRef(0)

  useEffect(() => {
    let socket: WebSocket | null = null
    let timer: number | undefined
    let stopped = false

    const connect = () => {
      dispatch({ type: 'connection', value: 'connecting' })
      socket = new WebSocket(liveUrl(missionId))
      socket.onopen = () => {
        retry.current = 0
        dispatch({ type: 'connection', value: 'open' })
      }
      socket.onmessage = (msg) => dispatch(JSON.parse(msg.data) as Event)
      socket.onclose = () => {
        dispatch({ type: 'connection', value: 'closed' })
        if (stopped) return
        const delay = Math.min(10_000, 1000 * 2 ** retry.current++)
        timer = window.setTimeout(connect, delay)
      }
    }
    connect()
    return () => {
      stopped = true
      window.clearTimeout(timer)
      socket?.close()
    }
  }, [missionId])

  const replaceDetection = useCallback((detection: Detection) => dispatch({ type: 'local_update', detection }), [])
  return { state, replaceDetection }
}
