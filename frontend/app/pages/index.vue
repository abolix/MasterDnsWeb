<script setup lang="ts">
definePageMeta({
  title: 'Dashboard'
})

const { hostMetrics, instances, updateHostMetrics } = useMasterDns()
const metricsInterval = ref<ReturnType<typeof setInterval> | null>(null)

onMounted(() => {
  updateHostMetrics()
  metricsInterval.value = setInterval(() => {
    updateHostMetrics()
  }, 5000)
})

onUnmounted(() => {
  if (metricsInterval.value) {
    clearInterval(metricsInterval.value)
  }
})

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
</script>

<template>
  <div class="space-y-8">
    <!-- Page Header -->
    <div>
      <h1 class="text-2xl font-bold tracking-tight text-neutral-900 dark:text-white">Dashboard</h1>
    </div>

    <!-- Status Summary Row -->
    <div class="grid grid-cols-2 gap-4 md:grid-cols-4">
      <div class="rounded-xl bg-linear-to-br from-emerald-500/10 to-emerald-600/5 p-4 ring-1 ring-emerald-500/20 dark:from-emerald-500/15 dark:to-emerald-600/5 dark:ring-emerald-500/10">
        <p class="text-xs font-medium text-emerald-700 dark:text-emerald-400">Running</p>
        <p class="mt-1 text-2xl font-bold text-emerald-900 dark:text-emerald-100">{{ runningCount }}</p>
      </div>
      <div class="rounded-xl bg-linear-to-br from-neutral-500/10 to-neutral-600/5 p-4 ring-1 ring-neutral-500/20 dark:from-neutral-500/15 dark:to-neutral-600/5 dark:ring-neutral-500/10">
        <p class="text-xs font-medium text-neutral-700 dark:text-neutral-400">Total Instances</p>
        <p class="mt-1 text-2xl font-bold text-neutral-900 dark:text-neutral-100">{{ totalCount }}</p>
      </div>
      <div class="rounded-xl bg-linear-to-br from-blue-500/10 to-blue-600/5 p-4 ring-1 ring-blue-500/20 dark:from-blue-500/15 dark:to-blue-600/5 dark:ring-blue-500/10">
        <p class="text-xs font-medium text-blue-700 dark:text-blue-400">Last Updated</p>
        <p class="mt-1 text-sm font-semibold text-blue-900 dark:text-blue-100">{{ new Date(hostMetrics.timestamp).toLocaleTimeString() }}</p>
      </div>
      <div class="rounded-xl bg-linear-to-br from-violet-500/10 to-violet-600/5 p-4 ring-1 ring-violet-500/20 dark:from-violet-500/15 dark:to-violet-600/5 dark:ring-violet-500/10">
        <p class="text-xs font-medium text-violet-700 dark:text-violet-400">Poll Interval</p>
        <p class="mt-1 text-2xl font-bold text-violet-900 dark:text-violet-100">5s</p>
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
    <UCard>
      <template #header>
        <div class="flex items-center justify-between">
          <h3 class="text-sm font-semibold text-neutral-900 dark:text-white">Active Instances</h3>
          <UButton to="/instances" variant="link" trailing-icon="i-lucide-arrow-right" size="sm">
            View All
          </UButton>
        </div>
      </template>

      <div v-if="instances.length === 0" class="py-8 text-center text-sm text-neutral-500">
        No instances yet. Create one from the Instances page.
      </div>

      <div v-else class="divide-y divide-neutral-200 dark:divide-neutral-800">
        <div
          v-for="instance in instances"
          :key="instance.id"
          class="flex items-center justify-between py-3 first:pt-0 last:pb-0"
        >
          <div class="flex items-center gap-3">
            <span
              class="h-2 w-2 rounded-full"
              :class="instance.status === 'running' ? 'bg-emerald-500' : 'bg-neutral-400'"
            />
            <span class="text-sm font-medium text-neutral-900 dark:text-white">{{ instance.name }}</span>
          </div>
          <UBadge
            :color="instance.status === 'running' ? 'success' : 'neutral'"
            variant="subtle"
            size="sm"
          >
            {{ instance.status }}
          </UBadge>
        </div>
      </div>
    </UCard>
  </div>
</template>
