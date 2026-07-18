import { useEffect, useRef, useState } from 'react'

const MOCK_REPLIES = [
  'Dạ em là trợ lý AI của Điện máy XANH, em có thể giúp gì cho anh/chị ạ? 😊',
  'Sản phẩm này hiện đang có chương trình giảm giá đến 50% trong tuần Lễ hội Worldcup ạ!',
  'Anh/chị muốn tìm máy lạnh, tủ lạnh hay tivi ạ? Em có thể gợi ý mẫu phù hợp với ngân sách.',
  'Dạ sản phẩm còn hàng ạ, anh/chị có thể đặt mua online hoặc ghé cửa hàng gần nhất.',
  'Em đã ghi nhận yêu cầu của anh/chị, nhân viên tư vấn sẽ liên hệ trong ít phút ạ.',
]

function initialMessages() {
  return [
    {
      id: 1,
      from: 'bot',
      text: 'Xin chào! Em là trợ lý AI của Điện máy XANH. Anh/chị cần tìm sản phẩm gì hôm nay ạ?',
    },
  ]
}

export default function ChatBubble() {
  const [open, setOpen] = useState(false)
  const [messages, setMessages] = useState(initialMessages)
  const [input, setInput] = useState('')
  const [typing, setTyping] = useState(false)
  const bodyRef = useRef(null)

  useEffect(() => {
    if (bodyRef.current) {
      bodyRef.current.scrollTop = bodyRef.current.scrollHeight
    }
  }, [messages, typing])

  const send = () => {
    const text = input.trim()
    if (!text) return
    setMessages((m) => [...m, { id: Date.now(), from: 'user', text }])
    setInput('')
    setTyping(true)

    // Mock reply — swap this block for a real API call to your AI backend.
    const reply = MOCK_REPLIES[Math.floor(Math.random() * MOCK_REPLIES.length)]
    setTimeout(() => {
      setTyping(false)
      setMessages((m) => [...m, { id: Date.now() + 1, from: 'bot', text: reply }])
    }, 900)
  }

  const onKeyDown = (e) => {
    if (e.key === 'Enter') send()
  }

  return (
    <div className="chat-widget">
      {open && (
        <div className="chat-panel">
          <div className="chat-panel__header">
            <div className="chat-panel__avatar">🤖</div>
            <div className="chat-panel__title">
              <strong>Trợ lý AI Điện máy XANH</strong>
              <span className="chat-panel__status">
                <i className="dot" /> Đang hoạt động
              </span>
            </div>
            <button className="chat-panel__close" onClick={() => setOpen(false)}>
              ✕
            </button>
          </div>

          <div className="chat-panel__body" ref={bodyRef}>
            {messages.map((m) => (
              <div key={m.id} className={`chat-bubble chat-bubble--${m.from}`}>
                {m.text}
              </div>
            ))}
            {typing && (
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
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={onKeyDown}
            />
            <button onClick={send} aria-label="Gửi">
              ➤
            </button>
          </div>
        </div>
      )}

      <button className="chat-fab" onClick={() => setOpen((o) => !o)} aria-label="Mở chat">
        <span className="chat-fab__icon">{open ? '✕' : '💬'}</span>
        {!open && <span className="chat-fab__badge">BETA</span>}
      </button>
    </div>
  )
}
