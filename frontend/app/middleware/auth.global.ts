export default defineNuxtRouteMiddleware(async (to) => {
  const { hasRestored, isAuthenticated, restoreSession } = useAuth()

  if (import.meta.server) {
    return
  }

  if (!hasRestored.value) {
    await restoreSession()
  }

  if (to.path === '/login') {
    if (isAuthenticated.value) {
      return navigateTo('/')
    }

    return
  }

  if (!isAuthenticated.value) {
    return navigateTo('/login')
  }
})
