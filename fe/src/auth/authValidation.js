export const PASSWORD_MIN_LENGTH = 8
export const PASSWORD_MAX_LENGTH = 128

export function validatePhone(phone) {
  const compact = String(phone || '').replace(/[\s().-]/g, '')
  if (!compact) return 'Vui lòng nhập số điện thoại.'
  if (!/^(?:\+84|0)(?:3|5|7|8|9)\d{8}$/.test(compact)) {
    return 'Số điện thoại Việt Nam chưa đúng định dạng.'
  }
  return ''
}

export function validatePassword(password) {
  if (!password) return 'Vui lòng nhập mật khẩu.'
  if (password.length < PASSWORD_MIN_LENGTH) {
    return `Mật khẩu cần ít nhất ${PASSWORD_MIN_LENGTH} ký tự.`
  }
  if (password.length > PASSWORD_MAX_LENGTH) {
    return `Mật khẩu không được quá ${PASSWORD_MAX_LENGTH} ký tự.`
  }
  return ''
}

export function getSafeReturnPath(candidate) {
  if (
    typeof candidate !== 'string' ||
    !candidate.startsWith('/') ||
    candidate.startsWith('//')
  ) {
    return '/'
  }

  const pathname = candidate.split(/[?#]/, 1)[0]
  if (pathname === '/login' || pathname === '/register') return '/'
  return candidate
}
