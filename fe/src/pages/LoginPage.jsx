import { useState } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/useAuth'
import {
  getSafeReturnPath,
  validatePassword,
  validatePhone,
} from '../auth/authValidation'
import AuthCard from '../components/auth/AuthCard'
import AuthPageShell from '../components/auth/AuthPageShell'
import PasswordField from '../components/auth/PasswordField'
import PhoneField from '../components/auth/PhoneField'

export default function LoginPage() {
  const { user, loading, login } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()
  const returnTo = getSafeReturnPath(location.state?.from)
  const [phone, setPhone] = useState('')
  const [password, setPassword] = useState('')
  const [errors, setErrors] = useState({})
  const [requestError, setRequestError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  if (!loading && user) {
    return <Navigate to={returnTo} replace />
  }

  const validate = () => {
    const nextErrors = {
      phone: validatePhone(phone),
      password: validatePassword(password),
    }
    setErrors(nextErrors)
    return !nextErrors.phone && !nextErrors.password
  }

  const submit = async (event) => {
    event.preventDefault()
    setRequestError('')
    if (!validate()) return

    setSubmitting(true)
    try {
      await login({ phone: phone.trim(), password })
      navigate(returnTo, { replace: true })
    } catch (error) {
      setRequestError(
        error?.message || 'Không thể đăng nhập lúc này. Vui lòng thử lại.',
      )
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <AuthPageShell>
      <AuthCard
        eyebrow="Chào mừng trở lại"
        title="Đăng nhập"
        description="Dùng số điện thoại và mật khẩu đã đăng ký."
        footer={
          <p>
            Chưa có tài khoản?{' '}
            <Link to="/register" state={{ from: returnTo }}>
              Đăng ký ngay
            </Link>
          </p>
        }
      >
        <form
          className="auth-form"
          onSubmit={submit}
          aria-busy={submitting}
          noValidate
        >
            <PhoneField
              value={phone}
              error={errors.phone}
              disabled={submitting}
              autoFocus
              onChange={(event) => {
                setPhone(event.target.value)
                setErrors((current) => ({ ...current, phone: '' }))
                setRequestError('')
              }}
              onBlur={() =>
                setErrors((current) => ({
                  ...current,
                  phone: validatePhone(phone),
                }))
              }
            />

            <PasswordField
              id="password"
              label="Mật khẩu"
              value={password}
              error={errors.password}
              disabled={submitting}
              autoComplete="current-password"
              onChange={(event) => {
                setPassword(event.target.value)
                setErrors((current) => ({ ...current, password: '' }))
                setRequestError('')
              }}
              onBlur={() =>
                setErrors((current) => ({
                  ...current,
                  password: validatePassword(password),
                }))
              }
            />

            {requestError && (
              <div className="auth-form__alert" role="alert">
                <span aria-hidden="true">!</span>
                {requestError}
              </div>
            )}

            <button
              className="auth-form__submit"
              type="submit"
              disabled={submitting}
              aria-busy={submitting}
            >
              {submitting ? (
                <LoadingLabel label="Đang đăng nhập" />
              ) : (
                'ĐĂNG NHẬP'
              )}
            </button>

            <p className="auth-form__note">
              Phiên đăng nhập được bảo vệ bằng cookie HttpOnly an toàn.
            </p>
        </form>
      </AuthCard>
    </AuthPageShell>
  )
}

function LoadingLabel({ label }) {
  return (
    <>
      <span className="auth-spinner auth-spinner--button" />
      {label}…
    </>
  )
}
