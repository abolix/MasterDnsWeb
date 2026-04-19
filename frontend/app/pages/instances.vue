<script setup lang="ts">
definePageMeta({
  title: 'Instances'
})

const { instances, selectedInstanceId, loadInstances, createInstance, deleteInstance, startInstance, stopInstance, restartInstance, fetchInstanceLogs, getInstanceLogs } = useMasterDns()
const toast = useToast()

const isCreateDialogOpen = ref(false)
const newInstanceName = ref('')
const isCreating = ref(false)

const selectedInstance = computed(() => {
  if (!selectedInstanceId.value) return null
  return instances.value.find(i => i.id === selectedInstanceId.value)
})

const recentLogs = computed(() => {
  if (!selectedInstance.value) return []
  return getInstanceLogs(selectedInstance.value.id, 10)
})

onMounted(async () => {
  try {
    await loadInstances()
  }
  catch (error: any) {
    toast.add({
      title: 'Failed to load instances',
      description: error?.data?.detail || 'Could not fetch instances from backend.',
      icon: 'i-lucide-circle-alert',
      color: 'error',
    })
  }
})

watch(
  () => selectedInstanceId.value,
  async (id) => {
    if (id) {
      await fetchInstanceLogs(id).catch(() => {})
    }
  },
  { immediate: true }
)

// Auto-refresh logs every 5 seconds for the selected instance
let logPollTimer: ReturnType<typeof setInterval> | null = null

function startLogPolling() {
  stopLogPolling()
  logPollTimer = setInterval(async () => {
    if (selectedInstanceId.value) {
      await fetchInstanceLogs(selectedInstanceId.value).catch(() => {})
    }
  }, 5000)
}

function stopLogPolling() {
  if (logPollTimer) {
    clearInterval(logPollTimer)
    logPollTimer = null
  }
}

watch(
  () => selectedInstanceId.value,
  (id) => {
    if (id) {
      startLogPolling()
    } else {
      stopLogPolling()
    }
  },
  { immediate: true }
)

onUnmounted(() => {
  stopLogPolling()
})

const autoScroll = ref(true)
const logsContainer = ref<HTMLElement | null>(null)

function getPortFromToml(toml: string): string | null {
  const match = toml.match(/^LISTEN_PORT\s*=\s*(\d+)/m)
  return match?.[1] ?? null
}

function getLocalDnsPort(toml: string): string | null {
  const match = toml.match(/^LOCAL_DNS_PORT\s*=\s*(\d+)/m)
  return match?.[1] ?? null
}

function isLocalDnsEnabled(toml: string): boolean {
  const match = toml.match(/^LOCAL_DNS_ENABLED\s*=\s*(\S+)/m)
  return match?.[1]?.toLowerCase() === 'true'
}

interface PortConflict {
  port: string
  type: 'listen' | 'local_dns'
  instanceNames: string[]
}

const portConflicts = computed((): PortConflict[] => {
  const conflicts: PortConflict[] = []

  // Check LISTEN_PORT conflicts
  const listenPortMap = new Map<string, string[]>()
  for (const inst of instances.value) {
    const port = getPortFromToml(inst.config_toml)
    if (!port) continue
    const existing = listenPortMap.get(port) ?? []
    existing.push(inst.name)
    listenPortMap.set(port, existing)
  }
  for (const [port, names] of listenPortMap) {
    if (names.length > 1) {
      conflicts.push({ port, type: 'listen', instanceNames: names })
    }
  }

  // Check LOCAL_DNS_PORT conflicts (only among instances with LOCAL_DNS_ENABLED = true)
  const localDnsPortMap = new Map<string, string[]>()
  for (const inst of instances.value) {
    if (!isLocalDnsEnabled(inst.config_toml)) continue
    const port = getLocalDnsPort(inst.config_toml)
    if (!port) continue
    const existing = localDnsPortMap.get(port) ?? []
    existing.push(inst.name)
    localDnsPortMap.set(port, existing)
  }
  for (const [port, names] of localDnsPortMap) {
    if (names.length > 1) {
      conflicts.push({ port, type: 'local_dns', instanceNames: names })
    }
  }

  return conflicts
})

function capitalize(s: string) {
  return s.charAt(0).toUpperCase() + s.slice(1)
}

const CRITICAL_KEYS: { key: string; label: string }[] = [
  { key: 'DOMAINS',                 label: 'DOMAINS' },
  { key: 'DATA_ENCRYPTION_METHOD',  label: 'DATA_ENCRYPTION_METHOD' },
  { key: 'ENCRYPTION_KEY',          label: 'ENCRYPTION_KEY' },
  { key: 'PROTOCOL_TYPE',           label: 'PROTOCOL_TYPE' },
  { key: 'LISTEN_IP',               label: 'LISTEN_IP' },
  { key: 'LISTEN_PORT',             label: 'LISTEN_PORT' },
  { key: 'SOCKS5_AUTH',             label: 'SOCKS5_AUTH' },
]

function tomlHasKey(toml: string, key: string): boolean {
  return new RegExp(`^${key}\\s*=`, 'm').test(toml)
}

function getMissingCriticalKeys(toml: string): string[] {
  const missing = CRITICAL_KEYS
    .filter(({ key }) => !tomlHasKey(toml, key))
    .map(({ label }) => label)

  // Only require SOCKS5_USER / SOCKS5_PASS when auth is enabled
  if (tomlHasKey(toml, 'SOCKS5_AUTH')) {
    const authLine = toml.match(/^SOCKS5_AUTH\s*=\s*(\S+)/m)
    const authEnabled = authLine?.[1]?.toLowerCase() === 'true'
    if (authEnabled) {
      if (!tomlHasKey(toml, 'SOCKS5_USER')) missing.push('SOCKS5_USER')
      if (!tomlHasKey(toml, 'SOCKS5_PASS')) missing.push('SOCKS5_PASS')
    }
  }

  return missing
}

const missingCriticalKeys = computed(() =>
  selectedInstance.value ? getMissingCriticalKeys(selectedInstance.value.config_toml) : []
)

watch(recentLogs, async () => {
  if (autoScroll.value) {
    await nextTick()
    if (logsContainer.value) {
      logsContainer.value.scrollTop = logsContainer.value.scrollHeight
    }
  }
}, { flush: 'post' })

async function handleCreateInstance() {
  if (!newInstanceName.value.trim()) return

  isCreating.value = true

  try {
    await createInstance(newInstanceName.value.trim())
    newInstanceName.value = ''
    isCreateDialogOpen.value = false
  }
  catch (error: any) {
    toast.add({
      title: 'Could not create instance',
      description: error?.data?.detail || error?.message || 'Please check the instance name and try again.',
      icon: 'i-lucide-circle-alert',
      color: 'error',
    })
  }
  finally {
    isCreating.value = false
  }
}

async function handleAction(instanceId: string, action: 'start' | 'stop' | 'restart') {
  const instance = instances.value.find(i => i.id === instanceId)
  if (!instance) return

  try {
    if (action === 'start') {
      await startInstance(instanceId)
    }
    else if (action === 'stop') {
      await stopInstance(instanceId)
    }
    else {
      await restartInstance(instanceId)
    }

    // Refresh logs after action
    await fetchInstanceLogs(instanceId).catch(() => {})

    const pastTense = action === 'stop' ? 'stopped' : `${action}ed`
    toast.add({
      title: `Service ${pastTense}`,
      description: `${instance.name} has been ${pastTense} successfully.`,
      icon: 'i-lucide-check-circle',
      color: 'success',
    })
  }
  catch (error: any) {
    toast.add({
      title: `Failed to ${action} service`,
      description: error?.data?.detail || error?.message || `Could not ${action} ${instance.name}.`,
      icon: 'i-lucide-circle-alert',
      color: 'error',
    })
  }
}

function selectInstance(id: string) {
  selectedInstanceId.value = id
}

function goToConfig(id: string) {
  navigateTo(`/config?instance=${id}`)
}

async function handleDeleteInstance(id: string) {
  try {
    await deleteInstance(id)
  }
  catch (error: any) {
    toast.add({
      title: 'Could not delete instance',
      description: error?.data?.detail || 'Backend rejected the delete request.',
      icon: 'i-lucide-circle-alert',
      color: 'error',
    })
  }
}
</script>

<template>
  <div class="space-y-8">
    <!-- Page Header -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold tracking-tight text-neutral-900 dark:text-white">Instances</h1>
      </div>

      <!-- Create Dialog: default slot = trigger, #body = content -->
      <UModal v-model:open="isCreateDialogOpen" title="Create New Instance">
        <UButton icon="i-lucide-plus" size="lg">New Instance</UButton>

        <template #body>
          <div class="space-y-4">
            <UFormField label="Instance Name" required>
              <UInput
                v-model="newInstanceName"
                placeholder="e.g., Secondary DNS, Test Instance"
                autofocus
                class="w-full"
                @keyup.enter="handleCreateInstance"
              />
            </UFormField>
          </div>
        </template>

        <template #footer>
          <div class="flex justify-end gap-2">
            <UButton variant="ghost" @click="isCreateDialogOpen = false">Cancel</UButton>
            <UButton @click="handleCreateInstance" :loading="isCreating">Create</UButton>
          </div>
        </template>
      </UModal>
    </div>

    <!-- Port Conflict Alerts -->
    <div v-if="portConflicts.length > 0" class="space-y-2">
      <div
        v-for="conflict in portConflicts"
        :key="`${conflict.type}-${conflict.port}`"
        class="flex items-start gap-3 rounded-xl bg-rose-50 px-4 py-3 ring-1 ring-rose-200 dark:bg-rose-900/20 dark:ring-rose-700/40"
      >
        <UIcon name="i-lucide-triangle-alert" class="mt-0.5 h-4 w-4 shrink-0 text-rose-600 dark:text-rose-400" />
        <p class="text-sm text-rose-800 dark:text-rose-300">
          <span class="font-semibold">Port conflict on {{ conflict.type === 'listen' ? 'LISTEN_PORT' : 'LOCAL_DNS_PORT' }} {{ conflict.port }}:</span>
          {{ conflict.instanceNames.join(', ') }} are using the same port. Only one instance can bind to a port at a time.
        </p>
      </div>
    </div>

    <!-- Instances Grid -->
    <div class="grid grid-cols-1 gap-6 lg:grid-cols-3">

      <!-- Instance List Sidebar -->
      <div class="lg:col-span-1 space-y-3">
        <h3 class="text-xs font-semibold tracking-wider text-neutral-500 uppercase dark:text-neutral-400">All Instances ({{ instances.length }})</h3>

        <div v-if="instances.length === 0" class="rounded-xl border border-dashed border-neutral-300 p-6 text-center dark:border-neutral-700">
          <UIcon name="i-lucide-server" class="mx-auto h-8 w-8 text-neutral-400" />
          <p class="mt-2 text-sm text-neutral-500">No instances yet.</p>
        </div>

        <div v-else class="space-y-1.5">
          <button
            v-for="instance in instances"
            :key="instance.id"
            @click="selectInstance(instance.id)"
            :class="[
              'group flex w-full items-center justify-between rounded-xl px-4 py-3 text-left transition-all',
              selectedInstanceId === instance.id
                ? 'bg-linear-to-r from-primary-500/10 to-primary-600/5 ring-1 ring-primary-500/30 dark:from-primary-500/15 dark:to-primary-600/5 dark:ring-primary-500/20'
                : 'hover:bg-neutral-100 dark:hover:bg-neutral-800/50'
            ]"
          >
            <div class="flex items-center gap-3">
              <span
                class="h-2.5 w-2.5 rounded-full ring-2 shrink-0"
                :class="instance.status === 'running'
                  ? 'bg-emerald-500 ring-emerald-500/20'
                  : 'bg-neutral-400 ring-neutral-400/20'"
              />
              <div class="flex items-center gap-2">
                <span class="text-sm font-medium text-neutral-900 dark:text-white">{{ instance.name }}</span>
                <span v-if="getPortFromToml(instance.config_toml)" class="block text-xs font-mono text-neutral-500 dark:text-neutral-400">:{{ getPortFromToml(instance.config_toml) }}</span>
              </div>
            </div>
            <UBadge
              :color="instance.status === 'running' ? 'success' : 'neutral'"
              variant="subtle"
              size="xs"
            >
              {{ capitalize(instance.status) }}
            </UBadge>
          </button>
        </div>
      </div>

      <!-- Instance Details -->
      <div v-if="selectedInstance" class="lg:col-span-2 space-y-5">

        <!-- Instance Header Card -->
        <div class="rounded-xl bg-linear-to-br from-neutral-50 to-neutral-100/50 p-5 ring-1 ring-neutral-200 dark:from-neutral-800/50 dark:to-neutral-900 dark:ring-neutral-700/50">
          <div class="flex items-start justify-between">
            <div>
              <h2 class="text-lg font-bold text-neutral-900 dark:text-white">{{ selectedInstance.name }}</h2>
              <p class="mt-1 text-xs text-neutral-500 dark:text-neutral-400">
                <template v-if="getPortFromToml(selectedInstance.config_toml)">
                  Port <span class="font-mono">{{ getPortFromToml(selectedInstance.config_toml) }}</span>
                  &nbsp;·&nbsp;
                </template>
                <span class="font-medium">{{ selectedInstance.resolvers.length }}</span> resolvers
              </p>
            </div>
            <UBadge
              :color="selectedInstance.status === 'running' ? 'success' : 'error'"
              variant="solid"
              size="md"
            >
              {{ capitalize(selectedInstance.status) }}
            </UBadge>
          </div>

          <!-- Missing critical config alert -->
          <div
            v-if="missingCriticalKeys.length > 0"
            class="mt-4 rounded-lg bg-amber-50 p-3 ring-1 ring-amber-200 dark:bg-amber-900/20 dark:ring-amber-700/40"
          >
            <div class="flex items-start justify-between gap-3">
              <div class="flex items-center gap-2">
                <UIcon name="i-lucide-triangle-alert" class="h-4 w-4 shrink-0 text-amber-600 dark:text-amber-400" />
                <p class="text-sm font-medium text-amber-800 dark:text-amber-300">Incomplete configuration</p>
              </div>
              <UButton
                icon="i-lucide-settings"
                color="warning"
                variant="soft"
                size="xs"
                class="shrink-0"
                @click="goToConfig(selectedInstance.id)"
              >
                Configure
              </UButton>
            </div>
          </div>

          <!-- Instance Metrics -->
          <div v-if="selectedInstance.metrics" class="mt-5 grid grid-cols-3 gap-4">
            <div class="rounded-lg bg-white/80 p-3 ring-1 ring-neutral-200/50 dark:bg-neutral-800/50 dark:ring-neutral-700/50">
              <p class="text-xs font-medium text-neutral-500 dark:text-neutral-400">CPU</p>
              <p class="mt-0.5 text-lg font-bold text-neutral-900 dark:text-white">{{ selectedInstance.metrics.cpu.toFixed(1) }}%</p>
            </div>
            <div class="rounded-lg bg-white/80 p-3 ring-1 ring-neutral-200/50 dark:bg-neutral-800/50 dark:ring-neutral-700/50">
              <p class="text-xs font-medium text-neutral-500 dark:text-neutral-400">Memory</p>
              <p class="mt-0.5 text-lg font-bold text-neutral-900 dark:text-white">{{ selectedInstance.metrics.memory.toFixed(1) }}%</p>
            </div>
            <div class="rounded-lg bg-white/80 p-3 ring-1 ring-neutral-200/50 dark:bg-neutral-800/50 dark:ring-neutral-700/50">
              <p class="text-xs font-medium text-neutral-500 dark:text-neutral-400">Uptime</p>
              <p class="mt-0.5 text-lg font-bold text-neutral-900 dark:text-white">{{ (selectedInstance.metrics.uptime_seconds / 3600).toFixed(1) }}h</p>
            </div>
          </div>

          <!-- Actions -->
          <div class="mt-5 rounded-xl bg-white/60 p-3 ring-1 ring-neutral-200/60 dark:bg-neutral-950/30 dark:ring-neutral-800/80">
            <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div class="flex flex-wrap items-center gap-2">
                <UButton
                  icon="i-lucide-play"
                  color="neutral"
                  variant="soft"
                  class="text-emerald-600 dark:text-emerald-400"
                  :disabled="selectedInstance.status === 'running'"
                  @click="handleAction(selectedInstance.id, 'start')"
                >
                  Start
                </UButton>
                <UButton
                  icon="i-lucide-square"
                  color="neutral"
                  variant="soft"
                  class="text-rose-600 dark:text-rose-400"
                  :disabled="selectedInstance.status === 'stopped'"
                  @click="handleAction(selectedInstance.id, 'stop')"
                >
                  Stop
                </UButton>
                <UButton
                  icon="i-lucide-rotate-cw"
                  color="neutral"
                  variant="soft"
                  class="text-amber-600 dark:text-amber-400"
                  @click="handleAction(selectedInstance.id, 'restart')"
                >
                  Restart
                </UButton>
              </div>

              <div class="flex flex-wrap items-center gap-2 sm:justify-end">
                <UButton
                  icon="i-lucide-settings"
                  color="neutral"
                  variant="outline"
                  @click="goToConfig(selectedInstance.id)"
                >
                  Configure
                </UButton>
                <UButton
                  icon="i-lucide-trash-2"
                  color="neutral"
                  variant="ghost"
                  class="text-rose-600 dark:text-rose-400"
                  @click="handleDeleteInstance(selectedInstance.id)"
                >
                  Delete
                </UButton>
              </div>
            </div>
          </div>
        </div>

        <!-- Recent Logs -->
        <UCard>
          <template #header>
            <div class="flex items-center justify-between gap-2">
              <div class="flex items-center gap-2">
                <UIcon name="i-lucide-terminal" class="h-4 w-4 text-neutral-500" />
                <span class="text-sm font-semibold text-neutral-900 dark:text-white">Recent Logs</span>
              </div>
              <label class="flex cursor-pointer select-none items-center gap-1.5">
                <input type="checkbox" v-model="autoScroll" class="rounded accent-primary-500" />
                <span class="text-xs text-neutral-500 dark:text-neutral-400">Auto-scroll</span>
              </label>
            </div>
          </template>

          <div ref="logsContainer" class="h-48 overflow-y-auto rounded-lg bg-neutral-950 p-4 font-mono text-xs leading-relaxed">
            <div v-if="recentLogs.length === 0" class="text-neutral-600">No logs yet.</div>
            <div v-for="(log, idx) in recentLogs" :key="idx" class="text-neutral-400">
              {{ log }}
            </div>
          </div>
        </UCard>
      </div>

      <!-- Empty State -->
      <div v-else class="lg:col-span-2 flex items-center justify-center">
        <div class="py-16 text-center">
          <div class="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl bg-linear-to-br from-neutral-100 to-neutral-200 dark:from-neutral-800 dark:to-neutral-700">
            <UIcon name="i-lucide-server" class="h-7 w-7 text-neutral-500 dark:text-neutral-400" />
          </div>
          <p class="mt-4 text-sm font-medium text-neutral-600 dark:text-neutral-400">Select an instance to view details</p>
          <p class="mt-1 text-xs text-neutral-400 dark:text-neutral-500">Or create a new one with the button above</p>
        </div>
      </div>
    </div>
  </div>
</template>
