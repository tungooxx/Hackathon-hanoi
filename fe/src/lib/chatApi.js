// Cầu nối FE -> BE1 (POST /chat, SSE stream).
// EventSource chỉ hỗ trợ GET nên ta tự parse SSE từ fetch body reader.
//
// BE1 events: funnel_count | question | text_chunk | product_cards | done
// (event type "_..." là internal, BE1 đã không forward).

import { apiFetch } from './apiClient'

/**
 * Gọi BE1 và dispatch từng event qua handlers.
 * @param {object} p
 * @param {string} p.sessionId  - giữ cố định theo phiên để BE1 nhớ hội thoại
 * @param {string} p.message
 * @param {AbortSignal} [p.signal]
 * @param {object} p.handlers - { onFunnel, onQuestion, onText, onProducts, onDone, onError }
 */
export async function streamChat({ sessionId, message, signal, handlers }) {
  const h = handlers || {}
  let res
  try {
    res = await apiFetch('/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, message }),
      signal,
    })
  } catch (e) {
    h.onError?.(e)
    return
  }
  if (!res.ok || !res.body) {
    h.onError?.(new Error(`BE1 HTTP ${res.status}`))
    return
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  try {
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      // sse-starlette dùng CRLF; chuẩn hoá về \n để tách event ổn định.
      buffer = (buffer + decoder.decode(value, { stream: true })).replace(/\r\n/g, '\n')

      // SSE: mỗi event ngăn cách bởi dòng trống (\n\n)
      let sep
      while ((sep = buffer.indexOf('\n\n')) !== -1) {
        const rawEvent = buffer.slice(0, sep)
        buffer = buffer.slice(sep + 2)
        dispatch(rawEvent, h)
      }
    }
  } catch (e) {
    if (e.name !== 'AbortError') h.onError?.(e)
  }
}

function dispatch(rawEvent, h) {
  const dataLines = rawEvent
    .split('\n')
    .filter((l) => l.startsWith('data:'))
    .map((l) => l.replace(/^data:\s?/, ''))
  if (!dataLines.length) return

  let evt
  try {
    evt = JSON.parse(dataLines.join('\n'))
  } catch {
    return
  }

  switch (evt.type) {
    case 'funnel_count':
      h.onFunnel?.({ count: evt.count, total: evt.total, filters: evt.filters })
      break
    case 'question':
      h.onQuestion?.({ slot: evt.slot, reason: evt.reason })
      break
    case 'text_chunk':
      h.onText?.(evt.content)
      break
    case 'product_cards':
      h.onProducts?.(evt.products)
      break
    case 'done':
      h.onDone?.(evt.turn_type)
      break
    default:
      break
  }
}

export function formatVnd(n) {
  if (n == null) return null
  return `${Math.round(n).toLocaleString('vi-VN')}đ`
}
