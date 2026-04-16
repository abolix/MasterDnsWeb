export const useAuth = () => {
  const isAuthenticated = useState('auth.isAuthenticated', () => false)
  const user = useState('auth.user', () => null as { username: string } | null)
  const isRestoring = useState('auth.isRestoring', () => false)
  const hasRestored = useState('auth.hasRestored', () => false)
  const config = useRuntimeConfig()

  const resolveApiBase = () => {
    if (config.public.apiBase) {
      return config.public.apiBase
    }

    if (import.meta.client) {
      const { protocol, hostname, port } = window.location

      if (port === '3000' || port === '3001') {
        return `${protocol}//${hostname}:8000`
      }

      return ''
    }

    return ''
  }

  const apiBase = resolveApiBase()

  const login = async (username: string, password: string) => {
    const response = await $fetch<{ username: string }>('/user-info', {
      baseURL: apiBase,
      method: 'GET',
      credentials: 'include',
      ignoreResponseError: true,
      onResponseError: () => undefined,
    })

    if (response?.username) {
      user.value = response
      isAuthenticated.value = true
      hasRestored.value = true
      return
    }

    await $fetch('/login', {
      baseURL: apiBase,
      method: 'POST',
      credentials: 'include',
      body: {
        username,
        password,
      },
    })

    user.value = await $fetch<{ username: string }>('/user-info', {
      baseURL: apiBase,
      method: 'GET',
      credentials: 'include',
    })
    isAuthenticated.value = true
    hasRestored.value = true
  }

  const logout = async () => {
    try {
      await $fetch('/logout', {
        baseURL: apiBase,
        method: 'POST',
        credentials: 'include',
      })
    }
    catch {
      // Clear local auth state even if the backend is already unreachable.
    }

    user.value = null
    isAuthenticated.value = false
    hasRestored.value = true
  }

  const restoreSession = async () => {
    if (isRestoring.value || hasRestored.value) {
      return
    }

    isRestoring.value = true

    try {
      user.value = await $fetch<{ username: string }>('/user-info', {
        baseURL: apiBase,
        method: 'GET',
        credentials: 'include',
      })
      isAuthenticated.value = true
    }
    catch {
      user.value = null
      isAuthenticated.value = false
    }
    finally {
      isRestoring.value = false
      hasRestored.value = true
    }
  }

  return {
    user: readonly(user),
    isAuthenticated: readonly(isAuthenticated),
    isRestoring: readonly(isRestoring),
    hasRestored: readonly(hasRestored),
    login,
    logout,
    restoreSession
  }
}
