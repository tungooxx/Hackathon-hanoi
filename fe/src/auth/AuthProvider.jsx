import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  getCurrentUser,
  loginUser,
  logoutUser,
  registerUser,
} from '../lib/authApi'
import { AuthContext } from './AuthContext'

const AUTH_BOOTSTRAP_TIMEOUT_MS = 5000

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)
  const authMutationVersion = useRef(0)

  useEffect(() => {
    let active = true
    const bootstrapVersion = authMutationVersion.current
    const controller = new AbortController()
    const timeoutId = window.setTimeout(
      () => controller.abort(),
      AUTH_BOOTSTRAP_TIMEOUT_MS,
    )

    getCurrentUser({ signal: controller.signal })
      .then((currentUser) => {
        if (
          active &&
          authMutationVersion.current === bootstrapVersion
        ) {
          setUser(currentUser)
        }
      })
      .catch(() => {
        if (
          active &&
          authMutationVersion.current === bootstrapVersion
        ) {
          setUser(null)
        }
      })
      .finally(() => {
        window.clearTimeout(timeoutId)
        if (active) setLoading(false)
      })

    return () => {
      active = false
    }
  }, [])

  const register = useCallback(async (credentials) => {
    authMutationVersion.current += 1
    setLoading(false)
    const session = await registerUser(credentials)
    setUser(session.user)
    return session.user
  }, [])

  const login = useCallback(async (credentials) => {
    authMutationVersion.current += 1
    setLoading(false)
    const session = await loginUser(credentials)
    setUser(session.user)
    return session.user
  }, [])

  const logout = useCallback(async () => {
    authMutationVersion.current += 1
    setLoading(false)
    try {
      await logoutUser()
    } finally {
      setUser(null)
    }
  }, [])

  const value = useMemo(
    () => ({ user, loading, register, login, logout }),
    [user, loading, register, login, logout],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
