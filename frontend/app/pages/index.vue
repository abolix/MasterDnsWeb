<script setup lang="ts">
definePageMeta({
  title: 'Dashboard'
})

const { hostMetrics, instances, updateHostMetrics } = useMasterDns()

// ── Polling ──────────────────────────────────────────────────────────────────
const POLL_INTERVAL = 5
let metricsTimer: ReturnType<typeof setInterval> | null = null
let tickTimer: ReturnType<typeof setInterval> | null = null
const secondsSinceUpdate = ref(0)
const lastUpdatedAt = ref(new Date())

onMounted(() => {
  updateHostMetrics()

  metricsTimer = setInterval(async () => {
    await updateHostMetrics()
    lastUpdatedAt.value = new Date()
    secondsSinceUpdate.value = 0
  }, POLL_INTERVAL * 1000)

  tickTimer = setInterval(() => {
    secondsSinceUpdate.value = Math.min(secondsSinceUpdate.value + 1, POLL_INTERVAL)
  }, 1000)
})

onUnmounted(() => {
  if (metricsTimer) clearInterval(metricsTimer)
  if (tickTimer) clearInterval(tickTimer)
})

const nextRefreshIn = computed(() => POLL_INTERVAL - secondsSinceUpdate.value)

// ── Metric colors ─────────────────────────────────────────────────────────────
const cpuColor = computed(() => {
  const cpu = hostMetrics.value.cpu
  if (cpu > 80) return 'error'
  if (cpu > 50) return 'warning'
  return 'success'
})

const memoryColor = computed(() => {
  const mem = hostMetrics.value.memory
  if (mem > 80) return 'error'
  if (mem > 60) return 'warning'
  return 'success'
})

const diskColor = computed(() => {
  const d = hostMetrics.value.disk_used_percent
  if (d > 85) return 'error'
  if (d > 60) return 'warning'
  return 'neutral'
})

const runningCount = computed(() => instances.value.filter(i => i.status === 'running').length)
const totalCount = computed(() => instances.value.length)

function getPortFromToml(toml: string): string | null {
  const match = toml.match(/^LISTEN_PORT\s*=\s*(\d+)/m)
  return match?.[1] ?? null
}

function capitalize(s: string) {
  return s.charAt(0).toUpperCase() + s.slice(1)
}

function getAuthLabel(toml: string): { enabled: boolean; user: string | null } | null {
  const match = toml.match(/^SOCKS5_AUTH\s*=\s*(\S+)/m)
  if (!match) return null
  const enabled = match[1]?.toLowerCase() === 'true'
  if (!enabled) return { enabled: false, user: null }
  const userMatch = toml.match(/^SOCKS5_USER\s*=\s*["']?([^"'\n\r]+?)["']?\s*$/m)
  return { enabled: true, user: userMatch?.[1]?.trim() ?? null }
}

const instancesWithMeta = computed(() =>
  instances.value.map(i => ({
    instance: i,
    port: getPortFromToml(i.config_toml),
    auth: getAuthLabel(i.config_toml),
  }))
)

</script>

<template>
  <div class="space-y-8">
    <!-- Page Header -->
    <div>
      <h1 class="text-2xl font-bold tracking-tight text-neutral-900 dark:text-white">Dashboard</h1>
    </div>

    <!-- Status Summary Row (3 cards: Running / Total / Live polling) -->
    <div class="grid grid-cols-1 gap-4 sm:grid-cols-3">
      <div class="rounded-xl bg-linear-to-br from-emerald-500/10 to-emerald-600/5 p-4 ring-1 ring-emerald-500/20 dark:from-emerald-500/15 dark:to-emerald-600/5 dark:ring-emerald-500/10">
        <p class="text-xs font-medium text-emerald-700 dark:text-emerald-400">Running</p>
        <p class="mt-1 text-2xl font-bold text-emerald-900 dark:text-emerald-100">{{ runningCount }}</p>
      </div>

      <div class="rounded-xl bg-linear-to-br from-neutral-500/10 to-neutral-600/5 p-4 ring-1 ring-neutral-500/20 dark:from-neutral-500/15 dark:to-neutral-600/5 dark:ring-neutral-500/10">
        <p class="text-xs font-medium text-neutral-700 dark:text-neutral-400">Total Instances</p>
        <p class="mt-1 text-2xl font-bold text-neutral-900 dark:text-neutral-100">{{ totalCount }}</p>
      </div>

      <!-- Combined polling card -->
      <div class="rounded-xl bg-linear-to-br from-blue-500/10 to-violet-500/5 p-4 ring-1 ring-blue-500/20 dark:from-blue-500/15 dark:to-violet-600/5 dark:ring-blue-500/10">
        <div class="flex items-center gap-1.5">
          <span class="h-1.5 w-1.5 animate-pulse rounded-full bg-blue-500"></span>
          <p class="text-xs font-medium text-blue-700 dark:text-blue-400">Live · every {{ POLL_INTERVAL }}s</p>
        </div>
        <p class="mt-1 text-sm font-bold text-blue-900 dark:text-blue-100">{{ lastUpdatedAt.toLocaleTimeString() }}</p>
        <p class="mt-0.5 text-xs text-blue-700/60 dark:text-blue-400/60">Next in {{ nextRefreshIn }}s</p>
      </div>
    </div>

    <!-- Metrics Cards -->
    <div class="grid grid-cols-1 gap-6 md:grid-cols-3">
      <!-- CPU -->
      <UCard>
        <div class="space-y-4">
          <div class="flex items-center gap-3">
            <div class="flex h-10 w-10 items-center justify-center rounded-lg bg-linear-to-br from-blue-500 to-blue-600 text-white">
              <UIcon name="i-lucide-cpu" class="h-5 w-5" />
            </div>
            <div>
              <p class="text-sm font-medium text-neutral-500 dark:text-neutral-400">CPU Usage</p>
              <p class="text-2xl font-bold text-neutral-900 dark:text-white">{{ hostMetrics.cpu.toFixed(1) }}%</p>
            </div>
          </div>
          <UProgress :model-value="hostMetrics.cpu" :color="cpuColor" size="sm" />
        </div>
      </UCard>

      <!-- Memory -->
      <UCard>
        <div class="space-y-4">
          <div class="flex items-center gap-3">
            <div class="flex h-10 w-10 items-center justify-center rounded-lg bg-linear-to-br from-violet-500 to-violet-600 text-white">
              <UIcon name="i-lucide-memory-stick" class="h-5 w-5" />
            </div>
            <div>
              <p class="text-sm font-medium text-neutral-500 dark:text-neutral-400">Memory Usage</p>
              <p class="text-2xl font-bold text-neutral-900 dark:text-white">{{ hostMetrics.memory.toFixed(1) }}%</p>
            </div>
          </div>
          <UProgress :model-value="hostMetrics.memory" :color="memoryColor" size="sm" />
        </div>
      </UCard>

      <!-- Disk -->
      <UCard>
        <div class="space-y-4">
          <div class="flex items-center gap-3">
            <div class="flex h-10 w-10 items-center justify-center rounded-lg bg-linear-to-br from-amber-500 to-amber-600 text-white">
              <UIcon name="i-lucide-hard-drive" class="h-5 w-5" />
            </div>
            <div>
              <p class="text-sm font-medium text-neutral-500 dark:text-neutral-400">Disk Usage</p>
              <p class="text-2xl font-bold text-neutral-900 dark:text-white">{{ hostMetrics.disk_used_percent.toFixed(1) }}%</p>
            </div>
          </div>
          <UProgress :model-value="hostMetrics.disk_used_percent" :color="diskColor" size="sm" />
        </div>
      </UCard>
    </div>

    <!-- Instance Quick View -->
    <div class="space-y-4">
      <!-- Section header -->
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-3">
          <h3 class="text-base font-semibold text-neutral-900 dark:text-white">Active Instances</h3>
          <span
            v-if="instances.length > 0"
            class="rounded-full bg-linear-to-r from-emerald-500/15 to-teal-500/10 px-2.5 py-0.5 text-xs font-semibold text-emerald-700 ring-1 ring-emerald-500/20 dark:text-emerald-400"
          >
            {{ runningCount }} / {{ totalCount }} running
          </span>
        </div>
        <UButton to="/instances" variant="ghost" trailing-icon="i-lucide-arrow-right" size="sm" color="neutral">
          View All
        </UButton>
      </div>

      <!-- Empty state -->
      <div
        v-if="instances.length === 0"
        class="flex flex-col items-center justify-center rounded-2xl border border-dashed border-neutral-300 py-14 dark:border-neutral-700"
      >
        <div class="mb-3 flex h-12 w-12 items-center justify-center rounded-xl bg-neutral-100 dark:bg-neutral-800">
          <UIcon name="i-lucide-server-off" class="h-6 w-6 text-neutral-400 dark:text-neutral-500" />
        </div>
        <p class="text-sm font-medium text-neutral-600 dark:text-neutral-400">No instances yet</p>
        <p class="mt-1 text-xs text-neutral-400 dark:text-neutral-500">Create one from the Instances page</p>
        <UButton to="/instances" size="sm" class="mt-4" variant="soft" color="neutral">
          Go to Instances
        </UButton>
      </div>

      <!-- Grid -->
      <div v-else class="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
        <NuxtLink
          v-for="{ instance, port, auth } in instancesWithMeta"
          :key="instance.id"
          to="/instances"
          class="group relative overflow-hidden rounded-2xl p-5 ring-1 transition-all duration-200 hover:-translate-y-0.5 hover:shadow-xl"
          :class="instance.status === 'running'
            ? 'bg-linear-to-br from-emerald-500/10 via-teal-400/5 to-cyan-500/5 ring-emerald-400/30 hover:shadow-emerald-500/10 dark:from-emerald-500/20 dark:via-teal-500/10 dark:to-cyan-500/5 dark:ring-emerald-500/25'
            : 'bg-linear-to-br from-neutral-100 to-slate-100 ring-neutral-200 hover:shadow-neutral-300/30 dark:from-neutral-800/60 dark:to-slate-900/40 dark:ring-neutral-700/50 dark:hover:shadow-neutral-900/30'"
        >
          <!-- Decorative glow orb — running only -->
          <div
            v-if="instance.status === 'running'"
            class="pointer-events-none absolute -right-8 -top-8 h-28 w-28 rounded-full bg-emerald-400/20 blur-2xl transition-opacity duration-300 group-hover:opacity-80 dark:bg-emerald-500/15"
          />

          <!-- Status row -->
          <div class="relative mb-4 flex items-center justify-between">
            <div class="flex items-center gap-2">
              <!-- Pinging dot for running -->
              <span v-if="instance.status === 'running'" class="relative flex h-2.5 w-2.5">
                <span class="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-70" />
                <span class="relative inline-flex h-2.5 w-2.5 rounded-full bg-emerald-500" />
              </span>
              <span v-else class="h-2.5 w-2.5 rounded-full bg-neutral-400 dark:bg-neutral-600" />
              <span
                class="text-xs font-bold uppercase tracking-widest"
                :class="instance.status === 'running'
                  ? 'text-emerald-600 dark:text-emerald-400'
                  : 'text-neutral-500 dark:text-neutral-400'"
              >
                {{ capitalize(instance.status) }}
              </span>
            </div>
            <!-- Slide-in arrow on hover -->
            <UIcon
              name="i-lucide-arrow-right"
              class="h-4 w-4 translate-x-1 text-neutral-400 opacity-0 transition-all duration-150 group-hover:translate-x-0 group-hover:opacity-100 dark:text-neutral-500"
            />
          </div>

          <!-- Instance name -->
          <p class="relative truncate text-[15px] font-bold text-neutral-900 dark:text-white">
            {{ instance.name }}
          </p>

          <!-- Port + Auth pills row -->
          <div class="relative mt-3 flex flex-wrap items-center gap-1.5">
            <span
              class="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-mono font-semibold ring-1"
              :class="instance.status === 'running'
                ? 'bg-emerald-500/10 text-emerald-700 ring-emerald-500/20 dark:bg-emerald-500/15 dark:text-emerald-300 dark:ring-emerald-500/25'
                : 'bg-neutral-200/80 text-neutral-600 ring-neutral-300 dark:bg-neutral-700/50 dark:text-neutral-400 dark:ring-neutral-600/50'"
            >
              <UIcon name="i-lucide-network" class="h-3 w-3 shrink-0" />
              {{ port ? `:${port}` : 'no port' }}
            </span>

            <template v-if="auth !== null">
              <span
                class="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold ring-1"
                :class="auth.enabled
                  ? 'bg-blue-500/10 text-blue-700 ring-blue-500/20 dark:bg-blue-500/15 dark:text-blue-300 dark:ring-blue-500/25'
                  : 'bg-neutral-200/60 text-neutral-500 ring-neutral-300/60 dark:bg-neutral-700/30 dark:text-neutral-400 dark:ring-neutral-600/40'"
              >
                <UIcon :name="auth.enabled ? 'i-lucide-lock' : 'i-lucide-lock-open'" class="h-3 w-3 shrink-0" />
                {{ auth.enabled ? 'Auth On' : 'No Auth' }}
              </span>
              <span
                v-if="auth.enabled && auth.user"
                class="inline-flex items-center gap-1 rounded-full bg-neutral-200/60 px-2 py-0.5 text-xs font-mono text-neutral-700 ring-1 ring-neutral-300/60 dark:bg-neutral-700/30 dark:text-neutral-300 dark:ring-neutral-600/40"
              >
                <UIcon name="i-lucide-user" class="h-3 w-3 shrink-0" />
                {{ auth.user }}
              </span>
            </template>
          </div>
        </NuxtLink>
      </div>
    </div>
  </div>
</template>
