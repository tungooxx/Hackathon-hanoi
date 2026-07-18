export default function AuthCard({
  eyebrow,
  title,
  description,
  children,
  footer,
}) {
  return (
    <section className="auth-card" aria-labelledby="auth-title">
      <div className="auth-card__heading">
        <span className="auth-card__eyebrow">{eyebrow}</span>
        <h1 id="auth-title">{title}</h1>
        {description && <p>{description}</p>}
      </div>

      {children}

      {footer && <div className="auth-card__footer">{footer}</div>}
    </section>
  )
}
