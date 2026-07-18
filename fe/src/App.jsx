import { Navigate, Route, Routes, useSearchParams } from 'react-router-dom'
import Header from './components/Header'
import Carousel from './components/Carousel'
import QuickCategoryGrid from './components/QuickCategoryGrid'
import PromoSection from './components/PromoSection'
import ChatBubble from './components/ChatBubble'
import LoginPopup from './components/LoginPopup'
import LoginPage from './pages/LoginPage'
import RegisterPage from './pages/RegisterPage'
import ProductResults from './pages/ProductResults'
import labelLeft from './assets/label-left.png'
import mascot from './assets/mascot-left.png'
import ball from './assets/ball-right.png'
import './App.css'

function HomePage() {
  const [searchParams] = useSearchParams()
  // Khách bấm "Còn N/M mẫu khớp" -> URL có ?category=... -> render danh sách
  // sản phẩm lọc ngay trên trang chính. Xoá param (hoặc "Về trang chủ") -> trang chính.
  if (searchParams.get('category')) {
    return <ProductResults />
  }

  return (
    <>
      <div className="stage">
        <img className="stage__label" src={labelLeft} alt="Worldcup 2026" />
        <img className="stage__mascot" src={mascot} alt="" aria-hidden="true" />
        <img className="stage__ball" src={ball} alt="" aria-hidden="true" />

        <main className="stage__center">
          <div className="hero-panel">
            <Carousel />
            <div className="ticker">
              <span className="ticker__icon">🪙</span>
              <span>
                MWG Paylater hạn mức đến <b>40 triệu</b>
              </span>
              <span className="ticker__dot">•</span>
              <span className="ticker__icon">💳</span>
              <span>
                Thẻ tín dụng VPBank MWG hạn mức đến <b>100 triệu</b>
              </span>
            </div>
            <QuickCategoryGrid />
          </div>

          <PromoSection />
        </main>
      </div>

      <LoginPopup />
    </>
  )
}

function App() {
  return (
    <div className="page">
      <Header />

      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>

      <ChatBubble />
    </div>
  )
}

export default App
