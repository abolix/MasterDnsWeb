// https://nuxt.com/docs/api/configuration/nuxt-config
export default defineNuxtConfig({
  app: {
    head: {
      title: 'MasterDNS',
      titleTemplate: '%s · MasterDNS'
    }
  },
  modules: ['@nuxt/ui', '@nuxtjs/color-mode'],
  ui: {
    fonts: false
  },
  css: ['~/assets/css/main.css'],
  runtimeConfig: {
    public: {
      apiBase: process.env.NUXT_PUBLIC_API_BASE || ''
    }
  },
  colorMode: {
    preference: 'system',
    fallback: 'light',
    classSuffix: ''
  },
  ssr: false,
  devtools: { enabled: true },
  compatibilityDate: '2025-07-15',
})
