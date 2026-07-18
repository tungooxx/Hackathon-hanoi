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

export default function RegisterPage() {
  const { user, loading, register } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()
  const returnTo = getSafeReturnPath(location.state?.from)
  const [values, setValues] = useState({
    phone: '',
    password: '',
    passwordConfirmation: '',
  })
  const [errors, setErrors] = useState({})
  const [requestError, setRequestError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  if (!loading && user) {
    return <Navigate to={returnTo} replace />
  }

  const updateValue = (field, value) => {
    setValues((current) => ({ ...current, [field]: value }))
    setErrors((current) => ({ ...current, [field]: '' }))
    setRequestError('')
  }

  const confirmationError = () => {
    if (!values.passwordConfirmation) return 'Vui lòng nhập lại mật khẩu.'
    if (values.passwordConfirmation !== values.password) {
      return 'Mật khẩu nhập lại chưa khớp.'
    }
    return ''
  }

  const validate = () => {
    const nextErrors = {
      phone: validatePhone(values.phone),
      password: validatePassword(values.password),
      passwordConfirmation: confirmationError(),
    }
    setErrors(nextErrors)
    return Object.values(nextErrors).every((error) => !error)
  }

  const submit = async (event) => {
    event.preventDefault()
    setRequestError('')
    if (!validate()) return

    setSubmitting(true)
    try {
      await register({
        phone: values.phone.trim(),
        password: values.password,
        passwordConfirmation: values.passwordConfirmation,
      })
      navigate(returnTo, { replace: true })
    } catch (error) {
      setRequestError(
        error?.message || 'Không thể đăng ký lúc này. Vui lòng thử lại.',
      )
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <AuthPageShell>
      <AuthCard
        eyebrow="Tạo tài khoản"
        title="Đăng ký"
        description="Số điện thoại sẽ là tên đăng nhập của bạn."
        footer={
          <p>
            Đã có tài khoản?{' '}
            <Link to="/login" state={{ from: returnTo }}>
              Đăng nhập
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
              value={values.phone}
              error={errors.phone}
              disabled={submitting}
              autoFocus
              onChange={(event) => updateValue('phone', event.target.value)}
              onBlur={() =>
                setErrors((current) => ({
                  ...current,
                  phone: validatePhone(values.phone),
                }))
              }
            />

            <PasswordField
              id="password"
              label="Mật khẩu"
              value={values.password}
              error={errors.password}
              disabled={submitting}
              autoComplete="new-password"
              placeholder="Tối thiểu 8 ký tự"
              onChange={(event) => updateValue('password', event.target.value)}
              onBlur={() =>
                setErrors((current) => ({
                  ...current,
                  password: validatePassword(values.password),
                }))
              }
            />

            <PasswordField
              id="passwordConfirmation"
              label="Nhập lại mật khẩu"
              value={values.passwordConfirmation}
              error={errors.passwordConfirmation}
              disabled={submitting}
              autoComplete="new-password"
              placeholder="Nhập lại mật khẩu"
              onChange={(event) =>
                updateValue('passwordConfirmation', event.target.value)
              }
              onBlur={() =>
                setErrors((current) => ({
                  ...current,
                  passwordConfirmation: confirmationError(),
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
                <>
                  <span className="auth-spinner auth-spinner--button" />
                  Đang tạo tài khoản…
                </>
              ) : (
                'TẠO TÀI KHOẢN'
              )}
            </button>

            <p className="auth-form__note">
              Khi đăng ký, bạn đồng ý cho hệ thống lưu số điện thoại để xác định
              tài khoản và phiên trò chuyện của bạn.
            </p>
        </form>
      </AuthCard>
    </AuthPageShell>
  )
}
