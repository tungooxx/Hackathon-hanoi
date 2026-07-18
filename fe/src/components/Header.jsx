import logo from '../assets/logo-wc.png'
import promoStrip from '../assets/promo-strip.png'
import { navCategories } from '../data/categories'

export default function Header() {
  return (
    <header className="site-header">
      <div className="promo-strip">
        <img src={promoStrip} alt="Chỉ 3 ngày từ 17 đến 19/7 Lễ hội Worldcup - Online giảm to" />
      </div>

      <div className="header-bar">
        <div className="header-main">
          <a href="/" className="logo">
            <img src={logo} alt="Điện máy XANH" />
          </a>

          <button className="category-btn">
            <span className="hamburger">☰</span>
            Danh mục
          </button>

          <div className="search-bar">
            <span className="search-icon">🔍</span>
            <input type="text" placeholder="Sunhouse xay ép thảnh thơi" readOnly />
          </div>

          <div className="header-actions">
            <a className="action-item" href="#login">
              <span className="icon">👤</span>
              Đăng nhập
            </a>
            <a className="action-item" href="#cart">
              <span className="icon">🛒</span>
              Giỏ hàng
            </a>
            <a className="action-item action-item--loc" href="#location">
              <span className="icon">📍</span>
              Hồ Chí Minh
              <span className="chevron">›</span>
            </a>
          </div>
        </div>
      </div>

      <nav className="category-nav">
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
