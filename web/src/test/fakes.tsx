import { act, render } from '@testing-library/react'
import { vi } from 'vitest'
import { App } from '../App'
import type { User } from '../types'

/** A request the page made to the faked backend. */
export interface Call {
  method: string
  path: string
  body: unknown
}

/** A reply other than 200 with JSON. */
export class Reply {
  constructor(
    readonly status: number,
    readonly body: unknown,
  ) {}
}

/** Per route ("GET /api/missions"): the JSON to answer with, a Reply, or a function of the request giving either. */
export type Routes = Record<string, unknown>

/**
 * Replaces fetch with a backend that answers from `routes` and records every request in the returned list. A route
 * it does not know gets a 404, so a page asking for something unexpected shows up in the test.
 */
export function fakeBackend(routes: Routes): Call[] {
  const calls: Call[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: string, init: RequestInit = {}) => {
      const method = init.method ?? 'GET'
      const path = new URL(input, window.location.origin).pathname
      const call = { method, path, body: init.body ? JSON.parse(String(init.body)) : undefined }
      calls.push(call)
      const route = routes[`${method} ${path}`]
      let answer = typeof route === 'function' ? route(call) : route
      if (answer === undefined) answer = new Reply(404, { detail: `No route ${method} ${path} in the test` })
      const reply = answer instanceof Reply ? answer : new Reply(200, answer)
      return new Response(JSON.stringify(reply.body), {
        status: reply.status,
        headers: { 'Content-Type': 'application/json' },
      })
    }),
  )
  return calls
}

/** A stored token the faked backend accepts for `user` (GET /api/auth/me), as after signing in earlier. */
export function signedInAs(user: User, routes: Routes): Routes {
  localStorage.setItem('uav.token', `token-${user.username}`)
  return { 'GET /api/auth/me': user, ...routes }
}

/** The app at `path`, as a browser opening that address. */
export function renderApp(path: string) {
  window.history.pushState({}, '', path)
  return render(<App />)
}

/** Stands in for the browser's WebSocket: the test opens the connection and sends the server's events. */
export class FakeWebSocket {
  static instances: FakeWebSocket[] = []

  onopen: ((e: Event) => void) | null = null
  onmessage: ((e: MessageEvent) => void) | null = null
  onclose: ((e: CloseEvent) => void) | null = null
  onerror: ((e: Event) => void) | null = null
  readyState = 0
  closed = false

  constructor(readonly url: string) {
    FakeWebSocket.instances.push(this)
  }

  send() {}

  close() {
    this.closed = true
    this.readyState = 3
  }

  /** Installs it as the WebSocket of the page; returns the list of sockets the page opens. */
  static install(): FakeWebSocket[] {
    FakeWebSocket.instances = []
    vi.stubGlobal('WebSocket', FakeWebSocket)
    return FakeWebSocket.instances
  }

  /** The server accepts the connection and sends `events`, as the backend does (a snapshot first). */
  serverOpens(...events: object[]) {
    act(() => {
      this.readyState = 1
      this.onopen?.(new Event('open'))
    })
    this.serverSends(...events)
  }

  serverSends(...events: object[]) {
    for (const event of events) {
      act(() => this.onmessage?.(new MessageEvent('message', { data: JSON.stringify(event) })))
    }
  }
}
