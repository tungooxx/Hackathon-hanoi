import { useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { useAuth } from '../auth/useAuth'

export default function LoginPopup() {
  const { user, loading } = useAuth()
  const location = useLocation()
  const [closed, setClosed] = useState(false)

  if (closed || loading || user) return null

  return (
    <div className="login-popup">
      <button
        className="login-popup__close"
        type="button"
        onClick={() => setClosed(true)}
        aria-label="Đóng gợi ý đăng nhập"
      >
        ✕
      </button>
      <Link
        to="/login"
        state={{
          from: `${location.pathname}${location.search}${location.hash}`,
        }}
        className="login-popup__card"
      >
        <span className="login-popup__ribbon" aria-hidden="true">
          🎁
        </span>
        <span className="login-popup__line1">ĐĂNG NHẬP</span>
        <span className="login-popup__line2">NHẬN</span>
        <span className="login-popup__line3">ƯU ĐÃI</span>
      </Link>
    </div>
  )
}
