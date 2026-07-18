import { useState } from 'react'

export default function LoginPopup() {
  const [closed, setClosed] = useState(false)
  if (closed) return null

  return (
    <div className="login-popup">
      <button
        className="login-popup__close"
        onClick={() => setClosed(true)}
        aria-label="Đóng"
      >
        ✕
      </button>
      <a href="#login" className="login-popup__card">
        <span className="login-popup__ribbon">🎁</span>
        <span className="login-popup__line1">ĐĂNG NHẬP</span>
        <span className="login-popup__line2">NHẬN</span>
        <span className="login-popup__line3">ƯU ĐÃI</span>
      </a>
    </div>
  )
}
