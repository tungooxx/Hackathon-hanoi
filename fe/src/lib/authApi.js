import { ApiError, apiRequest } from './apiClient'

const jsonHeaders = { 'Content-Type': 'application/json' }
const AUTH_REQUEST_TIMEOUT_MS = 10000

export function getCurrentUser({ signal } = {}) {
  return apiRequest('/auth/me', { signal })
}

export function registerUser({ phone, password, passwordConfirmation }) {
  return boundedAuthRequest('/auth/register', {
    method: 'POST',
    headers: jsonHeaders,
    body: JSON.stringify({
      phone,
      password,
      password_confirmation: passwordConfirmation,
    }),
    retryOnUnauthorized: false,
  })
}

export function loginUser({ phone, password }) {
  return boundedAuthRequest('/auth/login', {
    method: 'POST',
    headers: jsonHeaders,
    body: JSON.stringify({ phone, password }),
    retryOnUnauthorized: false,
  })
}

export function logoutUser() {
  return boundedAuthRequest('/auth/logout', {
    method: 'POST',
    retryOnUnauthorized: false,
  })
}

async function boundedAuthRequest(path, options) {
  const controller = new AbortController()
  const timeoutId = window.setTimeout(
    () => controller.abort(),
    AUTH_REQUEST_TIMEOUT_MS,
  )

  try {
    return await apiRequest(path, {
      ...options,
      signal: controller.signal,
    })
  } catch (error) {
    if (error?.name === 'AbortError') {
      throw new ApiError(
        'Máy chủ phản hồi quá lâu. Vui lòng kiểm tra BE1 và thử lại.',
        {
          code: 'request_timeout',
        },
      )
    }
    if (error instanceof TypeError) {
      throw new ApiError(
        'Không thể kết nối đến máy chủ. Vui lòng kiểm tra BE1 và thử lại.',
        {
          code: 'network_error',
        },
      )
    }
    throw error
  } finally {
    window.clearTimeout(timeoutId)
  }
}
