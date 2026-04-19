<script setup lang="ts">
const { logout, user } = useAuth()
const route = useRoute()
const colorMode = useColorMode()
const router = useRouter()
const isMobileMenuOpen = ref(false)

const { binaryVersion, fetchBinaryVersion } = useMasterDns()
onMounted(() => { void fetchBinaryVersion() })

const navItems = [
  { label: 'Dashboard', icon: 'i-lucide-gauge', to: '/' },
  { label: 'Instances', icon: 'i-lucide-server', to: '/instances' }
]

function toggleTheme() {
  colorMode.preference = colorMode.value === 'dark' ? 'light' : 'dark'
}

async function handleLogout() {
  await logout()
  await router.push('/login')
}
</script>

<template>
  <div class="flex h-screen flex-col bg-neutral-50 dark:bg-neutral-950">
    <!-- Top header -->
    <header class="relative z-10 border-b border-neutral-200/80 bg-white/80 backdrop-blur-lg dark:border-neutral-800/80 dark:bg-neutral-900/80">
      <div class="flex h-14 items-center justify-between px-6">
        <div class="flex items-center gap-3">
          <!-- Mobile menu button -->
          <UButton
            icon="i-lucide-menu"
            color="neutral"
            variant="ghost"
            size="sm"
            class="md:hidden"
            @click="isMobileMenuOpen = true"
          />
          <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-linear-to-br from-primary-500 to-primary-600">
            <UIcon name="i-lucide-shield" class="h-4 w-4 text-white" />
          </div>
          <span class="text-lg font-bold tracking-tight text-neutral-900 dark:text-white">MasterDNS</span>
        </div>
        <div class="flex items-center gap-2">
          <span class="hidden text-xs text-neutral-500 dark:text-neutral-400 sm:inline">{{ user?.username }}</span>
          <UButton
            :icon="colorMode.value === 'dark' ? 'i-lucide-sun' : 'i-lucide-moon'"
            color="neutral"
            variant="ghost"
            size="sm"
            @click="toggleTheme"
          />
          <UButton
            icon="i-lucide-log-out"
            color="neutral"
            variant="ghost"
            size="sm"
            @click="handleLogout"
          />
        </div>
      </div>
    </header>

    <!-- Mobile menu drawer -->
    <UDrawer v-model:open="isMobileMenuOpen" direction="left">
      <template #content>
        <div class="flex h-full flex-col bg-white/50 dark:bg-neutral-900/50">
          <div class="flex-1 space-y-1 p-3 pt-4">
            <NuxtLink
              v-for="item in navItems"
              :key="item.to"
              :to="item.to"
              @click="isMobileMenuOpen = false"
              :class="[
                'flex items-center gap-3 rounded-xl px-3.5 py-2.5 text-sm font-medium transition-all',
                route.path === item.to
                  ? 'bg-linear-to-r from-primary-500/10 to-primary-600/5 text-primary-700 ring-1 ring-primary-500/20 dark:from-primary-500/15 dark:to-primary-600/5 dark:text-primary-300 dark:ring-primary-500/15'
                  : 'text-neutral-600 hover:bg-neutral-100 hover:text-neutral-900 dark:text-neutral-400 dark:hover:bg-neutral-800/50 dark:hover:text-neutral-200'
              ]"
            >
              <UIcon :name="item.icon" class="h-4.5 w-4.5" />
              {{ item.label }}
            </NuxtLink>
          </div>

          <!-- Mobile sidebar footer -->
          <div class="border-t border-neutral-200/80 p-3 space-y-2 dark:border-neutral-800/80">
            <div class="space-y-1">
              <UButton
                to="https://github.com/masterking32/MasterDnsVPN"
                target="_blank"
                rel="noopener noreferrer"
                icon="i-simple-icons-github"
                color="neutral"
                variant="ghost"
                size="xs"
                class="w-full justify-start"
              >
                MasterDnsVPN
              </UButton>
              <UButton
                to="https://github.com/abolix/MasterDnsWeb/"
                target="_blank"
                rel="noopener noreferrer"
                icon="i-simple-icons-github"
                color="neutral"
                variant="ghost"
                size="xs"
                class="w-full justify-start"
              >
                MasterDnsWeb
              </UButton>
              <UButton
                to="https://t.me/masterdnsvpn"
                target="_blank"
                rel="noopener noreferrer"
                icon="i-simple-icons-telegram"
                color="neutral"
                variant="ghost"
                size="xs"
                class="w-full justify-start"
              >
                Telegram Channel
              </UButton>
            </div>
            <div class="rounded-xl bg-linear-to-br from-neutral-100 to-neutral-50 px-3 py-2.5 dark:from-neutral-800/50 dark:to-neutral-800/30">
              <p class="text-[10px] font-medium tracking-wider text-neutral-400 uppercase dark:text-neutral-500">Panel</p>
              <p class="mt-0.5 text-xs font-semibold text-neutral-600 dark:text-neutral-300">v1.0.2</p>
              <template v-if="binaryVersion">
                <p class="mt-1.5 text-[10px] font-medium tracking-wider text-neutral-400 uppercase dark:text-neutral-500">MasterDnsVPN</p>
                <p class="mt-0.5 text-xs font-semibold text-neutral-600 dark:text-neutral-300">{{ binaryVersion }}</p>
              </template>
            </div>
          </div>
        </div>
      </template>
    </UDrawer>

    <div class="flex flex-1 overflow-hidden">
      <!-- Sidebar -->
      <aside class="hidden w-56 border-r border-neutral-200/80 bg-white/50 md:flex md:flex-col dark:border-neutral-800/80 dark:bg-neutral-900/50">
        <nav class="flex-1 space-y-1 p-3 pt-4">
          <NuxtLink
            v-for="item in navItems"
            :key="item.to"
            :to="item.to"
            :class="[
              'flex items-center gap-3 rounded-xl px-3.5 py-2.5 text-sm font-medium transition-all',
              route.path === item.to
                ? 'bg-linear-to-r from-primary-500/10 to-primary-600/5 text-primary-700 ring-1 ring-primary-500/20 dark:from-primary-500/15 dark:to-primary-600/5 dark:text-primary-300 dark:ring-primary-500/15'
                : 'text-neutral-600 hover:bg-neutral-100 hover:text-neutral-900 dark:text-neutral-400 dark:hover:bg-neutral-800/50 dark:hover:text-neutral-200'
            ]"
          >
            <UIcon :name="item.icon" class="h-4.5 w-4.5" />
            {{ item.label }}
          </NuxtLink>
        </nav>

        <!-- Sidebar footer -->
        <div class="border-t border-neutral-200/80 p-3 space-y-2 dark:border-neutral-800/80">
          <div class="space-y-1">
            <UButton
              to="https://github.com/masterking32/MasterDnsVPN"
              target="_blank"
              rel="noopener noreferrer"
              icon="i-simple-icons-github"
              color="neutral"
              variant="ghost"
              size="xs"
              class="w-full justify-start"
            >
              MasterDnsVPN
            </UButton>
            <UButton
              to="https://github.com/abolix/MasterDnsWeb/"
              target="_blank"
              rel="noopener noreferrer"
              icon="i-simple-icons-github"
              color="neutral"
              variant="ghost"
              size="xs"
              class="w-full justify-start"
            >
              MasterDnsWeb
            </UButton>
            <UButton
              to="https://t.me/masterdnsvpn"
              target="_blank"
              rel="noopener noreferrer"
              icon="i-simple-icons-telegram"
              color="neutral"
              variant="ghost"
              size="xs"
              class="w-full justify-start"
            >
              Telegram Channel
            </UButton>
          </div>
          <div class="rounded-xl bg-linear-to-br from-neutral-100 to-neutral-50 px-3 py-2.5 dark:from-neutral-800/50 dark:to-neutral-800/30">
            <p class="text-[10px] font-medium tracking-wider text-neutral-400 uppercase dark:text-neutral-500">Panel</p>
            <p class="mt-0.5 text-xs font-semibold text-neutral-600 dark:text-neutral-300">v1.0.1</p>
            <template v-if="binaryVersion">
              <p class="mt-1.5 text-[10px] font-medium tracking-wider text-neutral-400 uppercase dark:text-neutral-500">MasterDnsVPN</p>
              <p class="mt-0.5 text-xs font-semibold text-neutral-600 dark:text-neutral-300">{{ binaryVersion }}</p>
            </template>
          </div>
        </div>
      </aside>

      <!-- Page content -->
      <main class="flex-1 overflow-auto">
        <div class="mx-auto px-6 py-8">
          <slot />
        </div>
      </main>
    </div>
  </div>
</template>
