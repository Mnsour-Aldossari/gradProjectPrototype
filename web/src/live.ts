import { useCallback, useEffect, useReducer, useRef, useState } from 'react'
import { api, getToken, liveUrl } from './api'
import type { Detection, LatLon, Mission, Telemetry } from './types'

const TRACE_LENGTH = 300 // ~30 s of sensor samples at the live event rate
const MAX_TRACK_POINTS = 20_000 // a long survey: the oldest points drop, so the page's memory stays bounded
const MAX_ALERTS = 50

export interface Alert {
  detection: Detection
  receivedAt: number
}

export interface LiveState {
  connection: 'connecting' | 'open' | 'closed' | 'failed'  // 'failed': gave up after repeated failures
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
  | {
      type: 'mission'
      status: Mission['status']
      phase?: Mission['phase']
      uav_source?: Mission['uav_source']
      progress: number
      battery_pct: number | null
      error: string | null
    } & Partial<Pick<Mission, 'sensor_collection' | 'sensor_reading_count' | 'sensor_coverage' | 'sensor_note'>>
  | { type: 'detection_created' | 'detection_updated'; detection: Detection }
  | { type: 'alert'; detection: Detection }
  | { type: 'detection_removed'; id: number }

type Action =
  | Event
  | { type: 'connection'; value: LiveState['connection'] }
  | { type: 'local_update'; detection: Detection }
  | { type: 'reset' }

const EVENT_TYPES = new Set([
  'snapshot',
  'telemetry',
  'mission',
  'detection_created',
  'detection_updated',
  'alert',
  'detection_removed',
])

/** A message from the server that has the shape of an event. A frame that does not is ignored, not dispatched. */
function isEvent(value: unknown): value is Event {
  return (
    typeof value === 'object' &&
    value !== null &&
    typeof (value as { type?: unknown }).type === 'string' &&
    EVENT_TYPES.has((value as { type: string }).type)
  )
}

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
    case 'reset':
      return { ...initial, connection: state.connection }
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
        track: [
          ...(state.track.length >= MAX_TRACK_POINTS ? state.track.slice(-(MAX_TRACK_POINTS - 1)) : state.track),
          [telemetry.lat, telemetry.lon],
        ],
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
              phase: action.phase ?? null,
              uav_source: action.uav_source ?? state.mission.uav_source,
              progress: action.progress,
              battery_pct: action.battery_pct,
              error: action.error,
              sensor_collection: action.sensor_collection ?? state.mission.sensor_collection,
              sensor_reading_count: action.sensor_reading_count ?? state.mission.sensor_reading_count,
              sensor_coverage: action.sensor_coverage ?? state.mission.sensor_coverage,
              sensor_note: action.sensor_note ?? state.mission.sensor_note,
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
        alerts: [{ detection: action.detection, receivedAt: Date.now() }, ...state.alerts].slice(0, MAX_ALERTS),
      }
    case 'detection_removed': {
      const { [action.id]: _removed, ...rest } = state.detections
      return { ...state, detections: rest }
    }
  }
}

/** Consecutive failed attempts before the live link stops retrying on its own. */
const MAX_RETRIES = 8

export function useMissionLive(missionId: number) {
  const [state, dispatch] = useReducer(reducer, initial)
  const [attempt, setAttempt] = useState(0)
  const retry = useRef(0)

  useEffect(() => {
    let socket: WebSocket | null = null
    let timer: number | undefined
    let stopped = false
    let opened = false

    dispatch({ type: 'reset' }) // another mission's detections and trace must not show while this one loads

    const connect = () => {
      opened = false
      dispatch({ type: 'connection', value: 'connecting' })
      socket = new WebSocket(liveUrl(missionId))
      // The token goes in the first message, not the address. The link counts as open once the server has accepted
      // it and answered with the snapshot: a rejected token closes the socket before that.
      socket.onopen = () => socket?.send(JSON.stringify({ type: 'auth', token: getToken() ?? '' }))
      socket.onmessage = (msg) => {
        let event: unknown
        try {
          event = JSON.parse(msg.data)
        } catch {
          return
        }
        if (!isEvent(event)) return
        if (!opened) {
          opened = true
          retry.current = 0
          dispatch({ type: 'connection', value: 'open' })
        }
        dispatch(event)
      }
      socket.onclose = () => {
        if (stopped) return
        if (retry.current >= MAX_RETRIES) {
          dispatch({ type: 'connection', value: 'failed' })
          return
        }
        dispatch({ type: 'connection', value: 'closed' })
        // A refused handshake (rejected token) looks like any other failure to the browser, so ask the API:
        // a 401 there ends the session and returns to the login page, which stops the retries.
        if (!opened) api('/api/auth/me').catch(() => undefined)
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
  }, [missionId, attempt])

  const replaceDetection = useCallback((detection: Detection) => dispatch({ type: 'local_update', detection }), [])
  /** Manual retry after the link gave up. */
  const reconnect = useCallback(() => {
    retry.current = 0
    setAttempt((n) => n + 1)
  }, [])
  return { state, replaceDetection, reconnect }
}
