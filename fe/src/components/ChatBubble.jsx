import { useEffect, useRef, useState } from 'react'
import { useAuth } from '../auth/useAuth'
import {
  createChatSession,
  formatVnd,
  streamChat,
  streamGuestChat,
  DEBUG_UI,
} from '../lib/chatApi'

function initialMessages() {
  return [
    {
      id: 1,
      from: 'bot',
      segments: ['Xin chào! 👋', 'Em là trợ lý AI của Điện máy XANH, anh/chị cần tìm sản phẩm gì hôm nay ạ?'],
    },
  ]
}

const PANEL_MIN_WIDTH = 300
const PANEL_MIN_HEIGHT = 360
const PANEL_MAX_WIDTH = 640
const PANEL_MAX_HEIGHT = 800

export default function ChatBubble() {
  const { user, loading: authLoading } = useAuth()
  const [open, setOpen] = useState(false)
  const [messages, setMessages] = useState(initialMessages)
  const [input, setInput] = useState('')
  const [typing, setTyping] = useState(false)
  const [panelSize, setPanelSize] = useState({ width: 340, height: 460 })
  const [resizing, setResizing] = useState(false)
  const bodyRef = useRef(null)
  // The public chat-session ID is created by BE1. The private LangGraph thread
  // ID never reaches the browser.
  const chatSessionId = useRef(null)
  const abortRef = useRef(null)
  const resizeStartRef = useRef(null)
  // khóa đồng bộ chống gửi lặp: state `typing` cập nhật bất đồng bộ nên hai
  // sự kiện Enter trong cùng một tick (thường gặp khi gõ tiếng Việt bằng IME)
  // đều thấy typing=false và cùng gửi -> trùng câu trả lời của bot.
  const sendingRef = useRef(false)
  // bộ đếm id đơn điệu, đảm bảo mỗi tin có id DUY NHẤT (Date.now() gọi nhiều
  // lần có thể trùng nhau -> user và bot dính chung id -> text bot đổ nhầm bong bóng)
  const msgSeq = useRef(0)
  const userId = user?.id

  useEffect(() => {
    abortRef.current?.abort()
    abortRef.current = null
    chatSessionId.current = null
    sendingRef.current = false
    msgSeq.current = 0
    setMessages(initialMessages())
    setInput('')
    setTyping(false)
    if (!userId) setOpen(false)
    return () => abortRef.current?.abort()
  }, [userId])

  const onResizeStart = (e) => {
    e.preventDefault()
    resizeStartRef.current = {
      x: e.clientX,
      y: e.clientY,
      width: panelSize.width,
      height: panelSize.height,
    }
    setResizing(true)
  }

  useEffect(() => {
    if (!resizing) return

    const onMove = (e) => {
      const start = resizeStartRef.current
      if (!start) return
      // Panel is anchored to bottom-right; kéo góc trên-trái => tăng width/height khi kéo ra ngoài (dx/dy âm)
      const dx = start.x - e.clientX
      const dy = start.y - e.clientY
      setPanelSize({
        width: Math.min(PANEL_MAX_WIDTH, Math.max(PANEL_MIN_WIDTH, start.width + dx)),
        height: Math.min(PANEL_MAX_HEIGHT, Math.max(PANEL_MIN_HEIGHT, start.height + dy)),
      })
    }
    const onUp = () => {
      resizeStartRef.current = null
      setResizing(false)
    }

    window.addEventListener('pointermove', onMove)
    window.addEventListener('pointerup', onUp)
    return () => {
      window.removeEventListener('pointermove', onMove)
      window.removeEventListener('pointerup', onUp)
    }
  }, [resizing])

  useEffect(() => {
    if (bodyRef.current) {
      bodyRef.current.scrollTop = bodyRef.current.scrollHeight
    }
  }, [messages, typing])

  // đóng/mở bảng "đang suy nghĩ" của từng tin bot
  const toggleActivity = (botId) =>
    patchBot(botId, (msg) => ({ activityOpen: !msg.activityOpen }))

  // nối 1 bước hành động (note / tool đang chạy) vào bong bóng bot
  const pushStep = (botId, step) =>
    patchBot(botId, (msg) => ({ actions: [...(msg.actions || []), step] }))

  // đánh dấu tool gần nhất cùng tên là xong + gắn count
  const finishTool = (botId, tool, count) =>
    patchBot(botId, (msg) => {
      const actions = [...(msg.actions || [])]
      for (let i = actions.length - 1; i >= 0; i--) {
        if (actions[i].kind === 'tool' && actions[i].tool === tool && actions[i].status === 'running') {
          actions[i] = { ...actions[i], status: 'done', count }
          break
        }
      }
      return { actions }
    })

  // cập nhật 1 phần của bong bóng bot đang stream
  const patchBot = (botId, patch) => {
    setMessages((m) =>
      m.map((msg) =>
        msg.id === botId
          ? { ...msg, ...(typeof patch === 'function' ? patch(msg) : patch) }
          : msg,
      ),
    )
  }

  // nối chunk text vào bong bóng cuối; gặp dòng trống ("\n\n") thì tách thành
  // bong bóng mới, mô phỏng người thật gửi nhiều tin nhắn ngắn liên tiếp
  const appendBotText = (botId, chunk) => {
    setMessages((m) =>
      m.map((msg) => {
        if (msg.id !== botId) return msg
        const segments = [...msg.segments]
        segments[segments.length - 1] += chunk
        let sepIdx
        while ((sepIdx = segments[segments.length - 1].indexOf('\n\n')) !== -1) {
          const last = segments.length - 1
          const head = segments[last].slice(0, sepIdx)
          const rest = segments[last].slice(sepIdx + 2).replace(/^\n+/, '')
          segments[last] = head
          segments.push(rest)
        }
        return { ...msg, segments }
      }),
    )
  }

  const send = async () => {
    const text = input.trim()
    if (!text || sendingRef.current || authLoading) return
    sendingRef.current = true

    const userMessageId = `u-${++msgSeq.current}`
    const botId = `b-${++msgSeq.current}`
    setMessages((m) => [
      ...m,
      { id: userMessageId, from: 'user', segments: [text] },
      { id: botId, from: 'bot', segments: [''], funnel: null, products: null, reason: null,
        actions: [], activityOpen: false },
    ])
    setInput('')
    setTyping(true)

    try {
      // Authenticated users receive a durable, owner-checked conversation.
      // Guests skip session creation and use the stateless endpoint below.
      if (!chatSessionId.current) {
        if (user) {
          const created = await createChatSession()
          chatSessionId.current = created.id
        }
      }
    } catch (error) {
      patchBot(botId, {
        segments: [
          error?.message ||
            'Không thể tạo cuộc trò chuyện. Anh/chị thử lại sau giúp em nhé. 🙏',
        ],
      })
      sendingRef.current = false
      setTyping(false)
      return
    }

    abortRef.current = new AbortController()
    const request = {
      message: text,
      signal: abortRef.current.signal,
      handlers: {
        onFunnel: (f) => patchBot(botId, { funnel: f }),
        onQuestion: (q) => patchBot(botId, { reason: q.reason }),
        onText: (chunk) => appendBotText(botId, chunk),
        onProducts: (products) => patchBot(botId, { products }),
        onAgentStep: (step) => pushStep(botId, step),
        onToolDone: ({ tool, count }) => finishTool(botId, tool, count),
        onDone: () => {
          sendingRef.current = false
          setTyping(false)
        },
        onError: (error) => {
          patchBot(botId, (msg) => ({
            segments: msg.segments.join('')
              ? msg.segments
              : [
                  error?.message ||
                    'Dạ hệ thống đang bận, anh/chị thử lại sau giúp em nhé. 🙏',
                ],
          }))
          sendingRef.current = false
          setTyping(false)
        },
      },
    }
    if (user) {
      streamChat({
        ...request,
        chatSessionId: chatSessionId.current,
      })
    } else {
      streamGuestChat(request)
    }
  }

  const onKeyDown = (e) => {
    // e.nativeEvent.isComposing / keyCode 229 = IME đang soạn (gõ tiếng Việt):
    // Enter lúc này chỉ để chốt ký tự, không phải để gửi tin.
    if (e.key !== 'Enter' || e.nativeEvent.isComposing || e.keyCode === 229) return
    e.preventDefault()
    send()
  }

  const toggleChat = () => {
    if (authLoading) return
    setOpen((current) => !current)
  }

  // tin bot đang stream = tin cuối khi đang chờ trả lời
  const activeBotId = typing ? messages[messages.length - 1]?.id : null
  const activeMsg = messages.find((m) => m.id === activeBotId)
  // đã có bảng "đang suy nghĩ" thì bỏ 3 chấm để tránh trùng chỉ báo
  const hideDots = DEBUG_UI && (activeMsg?.actions?.length || 0) > 0

  return (
    <div className="chat-widget">
      {open && (
        <div
          className={`chat-panel${resizing ? ' chat-panel--resizing' : ''}`}
          style={{
            '--chat-panel-width': `${panelSize.width}px`,
            '--chat-panel-height': `${panelSize.height}px`,
          }}
        >
          <div
            className="chat-panel__resize-handle"
            onPointerDown={onResizeStart}
            aria-label="Kéo để đổi kích thước"
          />
          <div className="chat-panel__header">
            <div className="chat-panel__avatar">🤖</div>
            <div className="chat-panel__title">
              <strong>Trợ lý AI Điện máy XANH</strong>
              <span className="chat-panel__status">
                <i className="dot" />{' '}
                {user ? 'Lưu theo tài khoản' : 'Khách · Không lưu lịch sử'}
              </span>
            </div>
            <button className="chat-panel__close" onClick={() => setOpen(false)}>
              ✕
            </button>
          </div>

          <div className="chat-panel__body" ref={bodyRef}>
            {messages.map((m) => (
              <div key={m.id} className={`chat-msg chat-msg--${m.from}`}>
                {DEBUG_UI && m.from === 'bot' && (m.actions?.length > 0 || m.id === activeBotId) && (
                  <AgentActivity
                    actions={m.actions || []}
                    open={m.activityOpen}
                    running={m.id === activeBotId}
                    onToggle={() => toggleActivity(m.id)}
                  />
                )}

                {m.funnel && (
                  <div className="chat-funnel">
                    🔎 Còn <b>{m.funnel.count}</b>/{m.funnel.total} mẫu khớp
                    {m.funnel.filters && Object.keys(m.funnel.filters).length > 0 && (
                      <span className="chat-funnel__filters">
                        {' '}
                        · {describeFilters(m.funnel.filters)}
                      </span>
                    )}
                  </div>
                )}

                {m.segments.filter(Boolean).map((seg, i) => (
                  <div key={i} className={`chat-bubble chat-bubble--${m.from}`}>
                    {seg}
                  </div>
                ))}

                {m.products && m.products.length > 0 && (
                  <div className="chat-cards">
                    {m.products.map((p) => (
                      <ProductCard key={p.sku || p.model_code || p.name} p={p} />
                    ))}
                  </div>
                )}
              </div>
            ))}

            {typing && !hideDots && (
              <div className="chat-bubble chat-bubble--bot chat-bubble--typing">
                <span />
                <span />
                <span />
              </div>
            )}
          </div>

          <div className="chat-panel__input">
            <input
              type="text"
              placeholder="Nhập câu hỏi của bạn..."
              value={input}
              disabled={typing}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={onKeyDown}
            />
            <button onClick={send} aria-label="Gửi" disabled={typing}>
              ➤
            </button>
          </div>
        </div>
      )}

      <button
        className="chat-fab"
        onClick={toggleChat}
        aria-label="Mở chat"
        disabled={authLoading}
      >
        <span className="chat-fab__icon">{open ? '✕' : '💬'}</span>
        {!open && <span className="chat-fab__badge">BETA</span>}
      </button>
    </div>
  )
}

// Bảng hành động của Agent ("đang suy nghĩ" -> click xổ chi tiết tool calling).
function AgentActivity({ actions, open, running, onToggle }) {
  const toolCount = actions.filter((a) => a.kind === 'tool').length
  const label = running
    ? 'Đang suy nghĩ…'
    : toolCount > 0
      ? `Đã dùng ${toolCount} công cụ`
      : 'Chi tiết xử lý'
  return (
    <div className={`agent-activity${running ? ' agent-activity--running' : ''}`}>
      <button className="agent-activity__head" onClick={onToggle} aria-expanded={open}>
        <span className="agent-activity__spark">{running ? '🧠' : '🛠️'}</span>
        <span className="agent-activity__label">{label}</span>
        <span className="agent-activity__chevron">{open ? '▾' : '▸'}</span>
      </button>
      {open && (
        <ul className="agent-activity__list">
          {actions.length === 0 && <li className="agent-activity__step">Đang khởi tạo…</li>}
          {actions.map((a, i) =>
            a.kind === 'tool' ? (
              <li key={i} className={`agent-activity__step agent-activity__step--${a.status}`}>
                <span className="agent-activity__ico">
                  {a.status === 'done' ? '✅' : '⏳'}
                </span>
                <span className="agent-activity__txt">
                  {a.label || a.tool}
                  {a.status === 'done' && a.count != null && (
                    <em className="agent-activity__count"> · {a.count} kết quả</em>
                  )}
                </span>
                <code className="agent-activity__tool">{a.tool}</code>
              </li>
            ) : (
              <li key={i} className="agent-activity__step agent-activity__step--note">
                <span className="agent-activity__ico">💬</span>
                <span className="agent-activity__txt">
                  {a.text}
                  {a.detail && <em className="agent-activity__detail">{a.detail}</em>}
                </span>
              </li>
            ),
          )}
        </ul>
      )}
    </div>
  )
}

function ProductCard({ p }) {
  const area =
    p.area_min_m2 != null && p.area_max_m2 != null
      ? `${p.area_min_m2}-${p.area_max_m2}m²`
      : null
  return (
    <div className="chat-card">
      <div className="chat-card__name">{p.name}</div>
      <div className="chat-card__price">
        {formatVnd(p.price_sale)}
        {p.price_original > p.price_sale && (
          <span className="chat-card__price-old">{formatVnd(p.price_original)}</span>
        )}
      </div>
      <div className="chat-card__specs">
        {p.energy_stars != null && <span>⭐ {p.energy_stars} sao điện</span>}
        {p.noise_db_min != null && <span>🔇 {p.noise_db_min}dB</span>}
        {area && <span>📐 {area}</span>}
        {p.inverter && <span>⚡ Inverter</span>}
      </div>
    </div>
  )
}

const SLOT_LABELS = {
  budget_max: 'ngân sách',
  area_m2: 'diện tích',
  brand: 'hãng',
}

function describeFilters(filters) {
  return Object.entries(filters)
    .map(([k, v]) => {
      const label = SLOT_LABELS[k] || k
      if (k === 'budget_max') return `${label} ≤ ${formatVnd(v)}`
      if (k === 'area_m2') return `${label} ${v}m²`
      return `${label}: ${v}`
    })
    .join(', ')
}
