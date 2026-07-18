// Cầu nối FE -> BE1 cho các phiên chat do server sở hữu.
// EventSource chỉ hỗ trợ GET nên ta tự parse SSE từ fetch body reader.
//
// BE1 events: funnel_count | question | text_chunk | product_cards | done
// (event type "_..." là internal, BE1 đã không forward).

import { ApiError, apiFetch, apiRequest } from './apiClient'

export function createChatSession(title) {
  return apiRequest('/chat/sessions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(title ? { title } : {}),
  })
}

export function listChatSessions({ limit = 50, offset = 0 } = {}) {
  const query = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  })
  return apiRequest(`/chat/sessions?${query}`)
}

export function getChatSession(chatSessionId) {
  return apiRequest(`/chat/sessions/${encodeURIComponent(chatSessionId)}`)
}

export function updateChatSession(chatSessionId, title) {
  return apiRequest(`/chat/sessions/${encodeURIComponent(chatSessionId)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  })
}

export function deleteChatSession(chatSessionId) {
  return apiRequest(`/chat/sessions/${encodeURIComponent(chatSessionId)}`, {
    method: 'DELETE',
  })
}

export function streamGuestChat({ message, signal, handlers }) {
  return streamMessage({
    path: '/chat/guest/messages',
    message,
    signal,
    handlers,
  })
}

// Bảng "đang suy nghĩ" (tool calling của Agent) hiển thị để debug.
// Mặc định (.env KHÔNG có VITE_DEBUG) -> hiện. Đặt VITE_DEBUG=False (production) -> ẩn.
export const DEBUG_UI =
  String(import.meta.env.VITE_DEBUG ?? 'true').toLowerCase() !== 'false'

/**
 * Gọi BE1 và dispatch từng event qua handlers.
 * @param {object} p
 * @param {string} p.chatSessionId - ID công khai do BE1 tạo và kiểm tra ownership
 * @param {string} p.message
 * @param {AbortSignal} [p.signal]
 * @param {object} p.handlers - { onFunnel, onQuestion, onText, onProducts, onDone, onError }
 */
export async function streamChat({ chatSessionId, message, signal, handlers }) {
  return streamMessage({
    path: `/chat/sessions/${encodeURIComponent(chatSessionId)}/messages`,
    message,
    signal,
    handlers,
  })
}

async function streamMessage({ path, message, signal, handlers }) {
  const h = handlers || {}
  let res
  try {
    res = await apiFetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message }),
      signal,
    })
  } catch (e) {
    h.onError?.(e)
    return
  }
  if (!res.ok || !res.body) {
    let payload = null
    try {
      payload = await res.json()
    } catch {
      // A non-JSON gateway error still receives a useful fallback below.
    }
    h.onError?.(
      new ApiError(
        payload?.error?.message || `Yêu cầu chat thất bại (${res.status}).`,
        {
          status: res.status,
          code: payload?.error?.code,
          details: payload?.error?.details,
        },
      ),
    )
    return
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let terminalEventReceived = false

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
        terminalEventReceived = dispatch(rawEvent, h) || terminalEventReceived
      }
    }
    if (!terminalEventReceived && !signal?.aborted) {
      h.onError?.(new Error('Kết nối tới trợ lý đã kết thúc ngoài dự kiến.'))
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
  if (!dataLines.length) return false

  let evt
  try {
    evt = JSON.parse(dataLines.join('\n'))
  } catch {
    return false
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
    // --- hành động của Agent (bảng "đang suy nghĩ") ---
    case 'enrich_note':
      h.onAgentStep?.({ kind: 'note', text: evt.message })
      break
    case 'tool_call':
      h.onAgentStep?.({ kind: 'tool', tool: evt.tool, label: evt.label, status: 'running' })
      break
    case 'tool_result':
      h.onToolDone?.({ tool: evt.tool, count: evt.count })
      break
    case 'web_specs': {
      const s = evt.spec || {}
      h.onAgentStep?.({
        kind: 'note',
        text: `Tra web: ${evt.product}${s.found === false ? ' — không có thông tin' : ''}`,
        detail: s.summary || null,
      })
      break
    }
    case 'done':
      h.onDone?.(evt.turn_type)
      return true
    case 'error':
      h.onError?.(new Error(evt.message || 'Trợ lý đang tạm thời gián đoạn.'))
      return true
    default:
      break
  }
  return false
}

export function formatVnd(n) {
  if (n == null) return null
  return `${Math.round(n).toLocaleString('vi-VN')}đ`
}
