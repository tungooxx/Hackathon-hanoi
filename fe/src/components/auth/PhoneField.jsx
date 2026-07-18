export default function PhoneField({
  id = 'phone',
  value,
  error,
  disabled,
  onChange,
  onBlur,
  autoFocus = false,
}) {
  const errorId = `${id}-error`

  return (
    <div className="auth-field">
      <label htmlFor={id}>Số điện thoại</label>
      <div className={`auth-input${error ? ' auth-input--error' : ''}`}>
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M7 2.75h10a2 2 0 0 1 2 2v14.5a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V4.75a2 2 0 0 1 2-2Zm0 2v13.5h10V4.75H7Zm4 15.25h2" />
        </svg>
        <input
          id={id}
          name="phone"
          type="tel"
          inputMode="tel"
          autoComplete="tel"
          placeholder="Nhập số điện thoại"
          value={value}
          disabled={disabled}
          aria-invalid={Boolean(error)}
          aria-describedby={error ? errorId : undefined}
          onChange={onChange}
          onBlur={onBlur}
          autoFocus={autoFocus}
          required
        />
      </div>
      {error && (
        <p className="auth-field__error" id={errorId}>
          {error}
        </p>
      )}
    </div>
  )
}
