import Header from './components/Header'
import Carousel from './components/Carousel'
import QuickCategoryGrid from './components/QuickCategoryGrid'
import PromoSection from './components/PromoSection'
import ChatBubble from './components/ChatBubble'
import LoginPopup from './components/LoginPopup'
import labelLeft from './assets/label-left.png'
import mascot from './assets/mascot-left.png'
import ball from './assets/ball-right.png'
import './App.css'

function App() {
  return (
    <div className="page">
      <Header />

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
      <ChatBubble />
    </div>
  )
}

export default App
