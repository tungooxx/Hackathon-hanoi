import { useEffect, useRef, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/useAuth'
import logo from '../assets/logo-wc.png'
import promoStrip from '../assets/promo-strip.png'
import { navCategories } from '../data/categories'

export default function Header() {
  const { user, loading, logout } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()
  const menuRef = useRef(null)
  const [menuOpen, setMenuOpen] = useState(false)
  const [loggingOut, setLoggingOut] = useState(false)
  const currentPath = `${location.pathname}${location.search}${location.hash}`
  const returnFrom = ['/login', '/register'].includes(location.pathname)
    ? '/'
    : currentPath

  useEffect(() => {
    setMenuOpen(false)
  }, [location.pathname])

  useEffect(() => {
    if (!menuOpen) return undefined

    const closeOnOutsideClick = (event) => {
      if (!menuRef.current?.contains(event.target)) setMenuOpen(false)
    }
    document.addEventListener('pointerdown', closeOnOutsideClick)
    return () => document.removeEventListener('pointerdown', closeOnOutsideClick)
  }, [menuOpen])

  const handleLogout = async () => {
    setLoggingOut(true)
    try {
      await logout()
      navigate('/', { replace: true })
    } finally {
      setLoggingOut(false)
      setMenuOpen(false)
    }
  }

  return (
    <header className="site-header">
      <div className="promo-strip">
        <img
          src={promoStrip}
          alt="Chỉ 3 ngày từ 17 đến 19/7 Lễ hội Worldcup - Online giảm to"
        />
      </div>

      <div className="header-bar">
        <div className="header-main">
          <Link to="/" className="logo" aria-label="Về trang chủ Điện máy XANH">
            <img src={logo} alt="Điện máy XANH" />
          </Link>

          <button className="category-btn" type="button">
            <span className="hamburger" aria-hidden="true">
              ☰
            </span>
            Danh mục
          </button>

          <div className="search-bar">
            <span className="search-icon" aria-hidden="true">
              🔍
            </span>
            <input
              type="text"
              aria-label="Tìm kiếm sản phẩm"
              placeholder="Sunhouse xay ép thảnh thơi"
              readOnly
            />
          </div>

          <div className="header-actions">
            {loading ? (
              <span className="action-item header-auth__loading" role="status">
                <span className="icon" aria-hidden="true">
                  👤
                </span>
                Đang tải…
              </span>
            ) : user ? (
              <div className="header-auth" ref={menuRef}>
                <button
                  className="action-item header-auth__trigger"
                  type="button"
                  aria-expanded={menuOpen}
                  aria-haspopup="menu"
                  onClick={() => setMenuOpen((current) => !current)}
                >
                  <span className="icon" aria-hidden="true">
                    👤
                  </span>
                  <span>{user.masked_phone}</span>
                  <span className="header-auth__caret" aria-hidden="true">
                    ▾
                  </span>
                </button>
                {menuOpen && (
                  <div className="header-auth__menu" role="menu">
                    <div className="header-auth__identity">
                      <span>Tài khoản của bạn</span>
                      <strong>{user.masked_phone}</strong>
                    </div>
                    <button
                      type="button"
                      role="menuitem"
                      disabled={loggingOut}
                      onClick={handleLogout}
                    >
                      <span aria-hidden="true">↪</span>
                      {loggingOut ? 'Đang đăng xuất…' : 'Đăng xuất'}
                    </button>
                  </div>
                )}
              </div>
            ) : (
              <Link
                className="action-item"
                to="/login"
                state={{ from: returnFrom }}
              >
                <span className="icon" aria-hidden="true">
                  👤
                </span>
                Đăng nhập
              </Link>
            )}
            <a className="action-item action-item--cart" href="#cart">
              <span className="icon" aria-hidden="true">
                🛒
              </span>
              Giỏ hàng
            </a>
            <a
              className="action-item action-item--loc action-item--location"
              href="#location"
            >
              <span className="icon" aria-hidden="true">
                📍
              </span>
              Hồ Chí Minh
              <span className="chevron" aria-hidden="true">
                ›
              </span>
            </a>
          </div>
        </div>
      </div>

      <nav className="category-nav" aria-label="Danh mục nổi bật">
        <div className="category-nav__inner">
          {navCategories.map((cat) => (
            <a key={cat} href="#" className="category-nav__item">
              {cat}
            </a>
          ))}
        </div>
      </nav>
    </header>
  )
}
