const configuredApiBase =
  import.meta.env?.VITE_API_BASE_URL || import.meta.env?.VITE_API_BASE

// Empty by default: the browser uses the Vite origin and Vite proxies
// /auth, /chat, and /health to BE1 during local development.
export const API_BASE_URL = configuredApiBase
  ? configuredApiBase.replace(/\/+$/, '')
  : ''

let refreshPromise = null

export class ApiError extends Error {
  constructor(message, { status = 0, code = 'request_failed', details = null } = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.details = details
  }
}

export function buildApiUrl(path) {
  if (/^https?:\/\//i.test(path)) return path
  return `${API_BASE_URL}${path.startsWith('/') ? path : `/${path}`}`
}

export async function apiFetch(
  path,
  { retryOnUnauthorized = true, ...options } = {},
) {
  const response = await fetch(buildApiUrl(path), {
    ...options,
    credentials: 'include',
  })

  if (
    response.status === 401 &&
    retryOnUnauthorized &&
    path !== '/auth/refresh'
  ) {
    try {
      await refreshSession(options.signal)
      return apiFetch(path, { ...options, retryOnUnauthorized: false })
    } catch {
      return response
    }
  }

  return response
}

export async function apiRequest(path, options = {}) {
  const response = await apiFetch(path, options)
  const payload = await readResponsePayload(response)

  if (!response.ok) {
    const apiError = payload?.error
    throw new ApiError(apiError?.message || `Yêu cầu thất bại (${response.status}).`, {
      status: response.status,
      code: apiError?.code,
      details: apiError?.details,
    })
  }

  return payload
}

async function refreshSession(signal) {
  if (!refreshPromise) {
    refreshPromise = fetch(buildApiUrl('/auth/refresh'), {
      method: 'POST',
      credentials: 'include',
      signal,
    })
      .then(async (response) => {
        if (!response.ok) {
          const payload = await readResponsePayload(response)
          throw new ApiError(
            payload?.error?.message || 'Không thể làm mới phiên đăng nhập.',
            {
              status: response.status,
              code: payload?.error?.code,
              details: payload?.error?.details,
            },
          )
        }
      })
      .finally(() => {
        refreshPromise = null
      })
  }

  return refreshPromise
}

async function readResponsePayload(response) {
  if (response.status === 204) return null

  const contentType = response.headers.get('content-type') || ''
  if (!contentType.includes('application/json')) return null

  try {
    return await response.json()
  } catch {
    return null
  }
}
