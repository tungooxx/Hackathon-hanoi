import mayLanh from '../../assets/prod/maylanh.jpg'
import mayGiat from '../../assets/prod/maygiat.jpg'
import tivi from '../../assets/prod/tivi.jpg'
import '../../pages/AuthPages.css'

const products = [
  { image: mayLanh, name: 'Máy lạnh Inverter', price: '8.490.000₫' },
  { image: tivi, name: 'Smart Tivi 4K', price: '6.990.000₫' },
  { image: mayGiat, name: 'Máy giặt cửa trước', price: '7.290.000₫' },
]

export default function AuthPageShell({ children }) {
  return (
    <main className="auth-page">
      <div className="auth-page__inner">
        <section className="auth-visual" aria-hidden="true">
          <div className="auth-visual__halo" />
          <span className="auth-visual__spark auth-visual__spark--one">✦</span>
          <span className="auth-visual__spark auth-visual__spark--two">✦</span>
          <span className="auth-visual__dot auth-visual__dot--one" />
          <span className="auth-visual__dot auth-visual__dot--two" />

          <div className="auth-phone">
            <div className="auth-phone__speaker" />
            <div className="auth-phone__header">
              <span />
              <strong>Mua sắm hôm nay</strong>
            </div>
            <div className="auth-phone__products">
              {products.map((product) => (
                <div className="auth-phone__product" key={product.name}>
                  <img src={product.image} alt="" />
                  <div>
                    <strong>{product.name}</strong>
                    <span>{product.price}</span>
                  </div>
                </div>
              ))}
            </div>
            <div className="auth-phone__home" />
          </div>

          <div className="auth-visual__bag">
            <span>✓</span>
          </div>
          <div className="auth-visual__card">
            <span className="auth-visual__chip" />
            <span className="auth-visual__card-line" />
            <strong>•••• 2026</strong>
          </div>

          <div className="auth-visual__copy">
            <strong>Mua sắm dễ dàng hơn</strong>
            <span>Đăng nhập để giữ trải nghiệm của riêng bạn.</span>
          </div>
        </section>

        <div className="auth-page__content">{children}</div>
      </div>
    </main>
  )
}
