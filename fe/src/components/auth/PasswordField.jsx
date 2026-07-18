import { useState } from 'react'

export default function PasswordField({
  id,
  label,
  value,
  error,
  disabled,
  autoComplete,
  placeholder = 'Nhập mật khẩu',
  onChange,
  onBlur,
}) {
  const [visible, setVisible] = useState(false)
  const errorId = `${id}-error`

  return (
    <div className="auth-field">
      <label htmlFor={id}>{label}</label>
      <div className={`auth-input${error ? ' auth-input--error' : ''}`}>
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M7.5 10V7.5a4.5 4.5 0 0 1 9 0V10M6 10h12a1.5 1.5 0 0 1 1.5 1.5v8A1.5 1.5 0 0 1 18 21H6a1.5 1.5 0 0 1-1.5-1.5v-8A1.5 1.5 0 0 1 6 10Zm6 4v3" />
        </svg>
        <input
          id={id}
          name={id}
          type={visible ? 'text' : 'password'}
          autoComplete={autoComplete}
          placeholder={placeholder}
          value={value}
          disabled={disabled}
          aria-invalid={Boolean(error)}
          aria-describedby={error ? errorId : undefined}
          onChange={onChange}
          onBlur={onBlur}
          required
        />
        <button
          className="auth-input__toggle"
          type="button"
          disabled={disabled}
          aria-label={visible ? `Ẩn ${label.toLowerCase()}` : `Hiện ${label.toLowerCase()}`}
          aria-pressed={visible}
          onClick={() => setVisible((current) => !current)}
        >
          {visible ? 'Ẩn' : 'Hiện'}
        </button>
      </div>
      {error && (
        <p className="auth-field__error" id={errorId}>
          {error}
        </p>
      )}
    </div>
  )
}
