import { useEffect, useRef, useState } from 'react'

export type WSStatus = 'connecting' | 'open' | 'closed'

/**
 * Generic reconnect/backoff WebSocket hook. `getUrl` is called fresh on every
 * connection attempt (not just once) — it must return null when a connection
 * shouldn't be attempted (e.g. no access token yet), and should read the
 * *current* access token each time, not one captured at mount: the token
 * refreshes independently in the background (see api/client.ts's interceptor),
 * and a reconnect after a 4401 needs to pick up a token that may have since
 * become valid.
 *
 * Backoff: exponential (1s base, ×2 per attempt, capped at 30s) with random
 * jitter so many tabs/clients reconnecting after a shared outage (e.g. the
 * backend restarting) don't all retry in the same instant and hit it at once.
 * The attempt counter resets to 0 on every successful open, so a connection
 * that's been stable for a while and drops once starts backing off from
 * scratch rather than carrying over a long delay from an outage hours ago.
 *
 * A 4401 close (this app's own code for "WS auth failed" — see backend
 * core/deps.py's require_ws_project_role/get_current_user_ws) starts backoff
 * from a higher base: retrying immediately with a token that was *just*
 * rejected is more likely to be hammering a genuinely-expired session than
 * catching a token that's about to be refreshed.
 */
export function useWebSocket(
  getUrl: () => string | null,
  onMessage: (data: unknown) => void,
  enabled = true,
): WSStatus {
  const [status, setStatus] = useState<WSStatus>('closed')
  const onMessageRef = useRef(onMessage)
  onMessageRef.current = onMessage

  useEffect(() => {
    if (!enabled) {
      setStatus('closed')
      return
    }

    let closedByEffect = false
    let attempt = 0
    let socket: WebSocket | null = null
    let reconnectTimer: ReturnType<typeof setTimeout> | undefined

    function scheduleReconnect(baseDelayMs: number) {
      const delay = Math.min(30_000, baseDelayMs * 2 ** attempt) + Math.random() * 500
      attempt += 1
      reconnectTimer = setTimeout(connect, delay)
    }

    function connect() {
      const url = getUrl()
      if (!url) {
        // No URL yet (e.g. token not loaded) — check back shortly rather than
        // giving up; this isn't a failed connection, just not-ready-yet.
        reconnectTimer = setTimeout(connect, 1000)
        return
      }

      setStatus('connecting')
      socket = new WebSocket(url)

      socket.onopen = () => {
        attempt = 0
        setStatus('open')
      }

      socket.onmessage = (event: MessageEvent<string>) => {
        try {
          onMessageRef.current(JSON.parse(event.data))
        } catch {
          // Malformed frame — drop it, not worth tearing down the connection.
        }
      }

      socket.onclose = (event: CloseEvent) => {
        setStatus('closed')
        if (closedByEffect) return
        scheduleReconnect(event.code === 4401 ? 5000 : 1000)
      }

      socket.onerror = () => {
        socket?.close()
      }
    }

    connect()

    return () => {
      closedByEffect = true
      clearTimeout(reconnectTimer)
      socket?.close()
    }
  }, [enabled, getUrl])

  return status
}
