<script setup lang="ts">
definePageMeta({
  title: 'Instances'
})

const { instances, selectedInstanceId, loadInstances, createInstance, deleteInstance, startInstance, stopInstance, restartInstance, fetchInstanceLogs, getInstanceLogs, updateInstanceConfig, exportInstance, importInstance, exportAllInstances, importAllInstances } = useMasterDns()
const toast = useToast()

const isCreateDialogOpen = ref(false)
const newInstanceName = ref('')
const isCreating = ref(false)
const isDeleteDialogOpen = ref(false)
const pendingDeleteId = ref<string | null>(null)
const isDuplicating = ref(false)
const importFileInput = ref<HTMLInputElement | null>(null)
const restoreFileInput = ref<HTMLInputElement | null>(null)
const isBackingUp = ref(false)

const pendingDeleteName = computed(() => {
  if (!pendingDeleteId.value) return ''
  return instances.value.find(i => i.id === pendingDeleteId.value)?.name ?? ''
})

const selectedInstance = computed(() => {
  if (!selectedInstanceId.value) return null
  return instances.value.find(i => i.id === selectedInstanceId.value)
})

const recentLogs = computed(() => {
  if (!selectedInstance.value) return []
  return getInstanceLogs(selectedInstance.value.id, 200)
})

const filteredLogs = computed(() => {
  if (!logSearch.value.trim()) return recentLogs.value
  const q = logSearch.value.toLowerCase()
  return recentLogs.value.filter(line => line.toLowerCase().includes(q))
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
const logSearch = ref('')
const isLogFullscreen = ref(false)
const fullscreenLogsContainer = ref<HTMLElement | null>(null)

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

function requestDeleteInstance(id: string) {
  pendingDeleteId.value = id
  isDeleteDialogOpen.value = true
}

async function confirmDeleteInstance() {
  const id = pendingDeleteId.value
  if (!id) return
  isDeleteDialogOpen.value = false
  pendingDeleteId.value = null
  try {
    await deleteInstance(id)
    toast.add({
      title: 'Instance deleted',
      description: `${id} has been removed.`,
      icon: 'i-lucide-check-circle',
      color: 'success',
    })
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

async function handleDuplicate() {
  if (!selectedInstance.value) return
  isDuplicating.value = true
  const src = selectedInstance.value
  const newName = `${src.name}-copy`

  try {
    await createInstance(newName)

    // Increment port to avoid conflict
    let toml = src.config_toml
    const currentPort = getPortFromToml(toml)
    if (currentPort) {
      toml = toml.replace(
        /^(LISTEN_PORT\s*=\s*)\d+/m,
        `$1${Number(currentPort) + 1}`
      )
    }
    await updateInstanceConfig(newName, toml, [...src.resolvers])
    // Backend restarts the service after a config update; stop it so the
    // user can adjust settings and port before starting manually.
    await stopInstance(newName).catch(() => {})

    toast.add({
      title: 'Instance duplicated',
      description: `Created ${newName} — configure the port and start when ready.`,
      icon: 'i-lucide-copy',
      color: 'success',
    })
  }
  catch (error: any) {
    toast.add({
      title: 'Could not duplicate instance',
      description: error?.data?.detail || error?.message || 'Duplication failed.',
      icon: 'i-lucide-circle-alert',
      color: 'error',
    })
  }
  finally {
    isDuplicating.value = false
  }
}

async function handleExport() {
  if (!selectedInstance.value) return
  try {
    await exportInstance(selectedInstance.value.id)
    toast.add({ title: 'Exported', description: `${selectedInstance.value.name}.json downloaded.`, icon: 'i-lucide-download', color: 'success' })
  }
  catch (error: any) {
    toast.add({ title: 'Export failed', description: error?.data?.detail || error?.message || 'Could not export.', icon: 'i-lucide-circle-alert', color: 'error' })
  }
}

async function handleImport(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  input.value = ''
  try {
    await importInstance(file)
    toast.add({ title: 'Imported', description: `${file.name} imported successfully.`, icon: 'i-lucide-upload', color: 'success' })
  }
  catch (error: any) {
    toast.add({ title: 'Import failed', description: error?.data?.detail || error?.message || 'Could not import.', icon: 'i-lucide-circle-alert', color: 'error' })
  }
}

async function handleBackupAll() {
  isBackingUp.value = true
  try {
    await exportAllInstances()
    toast.add({ title: 'Backup downloaded', description: 'masterdns-backup.zip saved.', icon: 'i-lucide-archive', color: 'success' })
  }
  catch (error: any) {
    toast.add({ title: 'Backup failed', description: error?.data?.detail || error?.message || 'Could not create backup.', icon: 'i-lucide-circle-alert', color: 'error' })
  }
  finally {
    isBackingUp.value = false
  }
}

async function handleRestoreAll(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  input.value = ''
  try {
    const result = await importAllInstances(file)
    const desc = `Created: ${result.created.length}${result.errors.length ? `, Errors: ${result.errors.length}` : ''}`
    toast.add({ title: 'Restore complete', description: desc, icon: 'i-lucide-archive-restore', color: result.errors.length ? 'warning' : 'success' })
  }
  catch (error: any) {
    toast.add({ title: 'Restore failed', description: error?.data?.detail || error?.message || 'Could not restore.', icon: 'i-lucide-circle-alert', color: 'error' })
  }
}

// ── Telegram SOCKS5 proxy link (per selected instance) ────────────────────────
const serverHost = ref('')
onMounted(() => {
  serverHost.value = window.location.hostname
})
const isLocalhost = computed(() =>
  !serverHost.value ||
  serverHost.value === 'localhost' ||
  serverHost.value === '127.0.0.1' ||
  serverHost.value === '::1'
)

function getTomlField(toml: string, key: string): string | null {
  const match = toml.match(new RegExp(`^${key}\\s*=\\s*(.+)$`, 'm'))
  const raw = match?.[1]
  if (!raw) return null
  return raw.trim().replace(/^["']|["']$/g, '').trim() || null
}

interface TelegramProxy { link: string | null; warning: string | null }

const telegramProxy = computed((): TelegramProxy | null => {
  if (!selectedInstance.value) return null
  const toml = selectedInstance.value.config_toml
  if (getTomlField(toml, 'PROTOCOL_TYPE')?.toUpperCase() !== 'SOCKS5') return null

  const port = getTomlField(toml, 'LISTEN_PORT')
  if (!port) return { link: null, warning: 'LISTEN_PORT not set' }

  const authEnabled = getTomlField(toml, 'SOCKS5_AUTH')?.toLowerCase() === 'true'
  if (authEnabled) {
    const user = getTomlField(toml, 'SOCKS5_USER')
    const pass = getTomlField(toml, 'SOCKS5_PASS')
    if (!user || !pass) return { link: null, warning: 'Auth enabled but SOCKS5_USER / SOCKS5_PASS not set' }
    return {
      link: `tg://socks?server=${serverHost.value}&port=${port}&user=${encodeURIComponent(user)}&pass=${encodeURIComponent(pass)}`,
      warning: null,
    }
  }
  return { link: `tg://socks?server=${serverHost.value}&port=${port}`, warning: null }
})

async function copyLink(link: string) {
  try {
    if (navigator.clipboard) {
      await navigator.clipboard.writeText(link)
    } else {
      const el = document.createElement('textarea')
      el.value = link
      el.style.position = 'fixed'
      el.style.opacity = '0'
      document.body.appendChild(el)
      el.focus()
      el.select()
      document.execCommand('copy')
      document.body.removeChild(el)
    }
    toast.add({ title: 'Copied!', icon: 'i-lucide-check', color: 'success' })
  }
  catch {
    toast.add({ title: 'Could not copy to clipboard', icon: 'i-lucide-x', color: 'error' })
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
      <div class="flex items-center gap-2">
        <UButton icon="i-lucide-archive" size="sm" variant="outline" color="neutral" :loading="isBackingUp" @click="handleBackupAll">
          Backup
        </UButton>
        <UButton icon="i-lucide-archive-restore" size="sm" variant="outline" color="neutral" @click="restoreFileInput?.click()">
          Restore
        </UButton>
        <input ref="restoreFileInput" type="file" accept=".zip" class="hidden" @change="handleRestoreAll" />
        <UButton icon="i-lucide-upload" size="sm" variant="outline" color="neutral" @click="importFileInput?.click()">
          Import
        </UButton>
        <input ref="importFileInput" type="file" accept=".json" class="hidden" @change="handleImport" />
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

      <!-- Delete Confirmation -->
      <UModal v-model:open="isDeleteDialogOpen" title="Delete Instance">
        <template #default />
        <template #body>
          <div class="space-y-3">
            <div class="flex items-center gap-3 rounded-lg bg-rose-50 p-3 ring-1 ring-rose-200 dark:bg-rose-900/20 dark:ring-rose-700/40">
              <UIcon name="i-lucide-triangle-alert" class="h-5 w-5 shrink-0 text-rose-600 dark:text-rose-400" />
              <p class="text-sm text-rose-800 dark:text-rose-300">This action cannot be undone.</p>
            </div>
            <p class="text-sm text-neutral-600 dark:text-neutral-400">
              This will stop the service, remove the systemd unit, and delete all configuration for
              <span class="font-semibold text-neutral-900 dark:text-white">{{ pendingDeleteName }}</span>.
            </p>
          </div>
        </template>
        <template #footer>
          <div class="flex justify-end gap-2">
            <UButton variant="ghost" @click="isDeleteDialogOpen = false">Cancel</UButton>
            <UButton color="error" @click="confirmDeleteInstance">Delete</UButton>
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
                <template v-if="getTomlField(selectedInstance.config_toml, 'PROTOCOL_TYPE')">
                  <span class="font-semibold">{{ getTomlField(selectedInstance.config_toml, 'PROTOCOL_TYPE') }}</span>
                  &nbsp;·&nbsp;
                </template>
                <template v-if="getPortFromToml(selectedInstance.config_toml)">
                  Port <span class="font-mono">{{ getPortFromToml(selectedInstance.config_toml) }}</span>
                  &nbsp;·&nbsp;
                </template>
                <span class="font-medium">{{ selectedInstance.resolvers.length }}</span> resolvers
              </p>

              <!-- Auth chips -->
              <div
                v-if="getTomlField(selectedInstance.config_toml, 'SOCKS5_AUTH') !== null"
                class="mt-2 flex flex-wrap items-center gap-1.5"
              >
                <span
                  class="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold ring-1"
                  :class="getTomlField(selectedInstance.config_toml, 'SOCKS5_AUTH')?.toLowerCase() === 'true'
                    ? 'bg-blue-50 text-blue-700 ring-blue-200 dark:bg-blue-500/15 dark:text-blue-300 dark:ring-blue-500/25'
                    : 'bg-neutral-100 text-neutral-500 ring-neutral-200 dark:bg-neutral-700/40 dark:text-neutral-400 dark:ring-neutral-600/50'"
                >
                  <UIcon
                    :name="getTomlField(selectedInstance.config_toml, 'SOCKS5_AUTH')?.toLowerCase() === 'true' ? 'i-lucide-lock' : 'i-lucide-lock-open'"
                    class="h-3 w-3 shrink-0"
                  />
                  {{ getTomlField(selectedInstance.config_toml, 'SOCKS5_AUTH')?.toLowerCase() === 'true' ? 'Auth Enabled' : 'No Auth' }}
                </span>
                <span
                  v-if="getTomlField(selectedInstance.config_toml, 'SOCKS5_AUTH')?.toLowerCase() === 'true' && getTomlField(selectedInstance.config_toml, 'SOCKS5_USER')"
                  class="inline-flex items-center gap-1 rounded-full bg-neutral-100 px-2 py-0.5 text-xs font-mono text-neutral-700 ring-1 ring-neutral-200 dark:bg-neutral-700/40 dark:text-neutral-300 dark:ring-neutral-600/50"
                >
                  <UIcon name="i-lucide-user" class="h-3 w-3 shrink-0" />
                  {{ getTomlField(selectedInstance.config_toml, 'SOCKS5_USER') }}
                </span>
              </div>
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
                  icon="i-lucide-download"
                  size="sm"
                  color="neutral"
                  variant="outline"
                  @click="handleExport"
                >
                  Export
                </UButton>
                <UButton
                  icon="i-lucide-copy"
                  size="sm"
                  color="neutral"
                  variant="outline"
                  :loading="isDuplicating"
                  @click="handleDuplicate"
                >
                  Duplicate
                </UButton>
                <UButton
                  icon="i-lucide-settings"
                  size="sm"
                  color="neutral"
                  variant="outline"
                  @click="goToConfig(selectedInstance.id)"
                >
                  Configure
                </UButton>
                <UButton
                  icon="i-lucide-trash-2"
                  size="sm"
                  color="neutral"
                  variant="ghost"
                  class="text-rose-600 dark:text-rose-400"
                  @click="requestDeleteInstance(selectedInstance.id)"
                >
                  Delete
                </UButton>
              </div>
            </div>
          </div>
        </div>

        <!-- Telegram Proxy Link -->
        <UCard v-if="telegramProxy && selectedInstance?.status === 'running'">
          <template #header>
            <div class="flex items-center gap-2">
              <UIcon name="i-simple-icons-telegram" class="h-4 w-4 text-neutral-500" />
              <h3 class="text-sm font-semibold text-neutral-900 dark:text-white">Telegram Proxy Link</h3>
            </div>
          </template>

          <!-- Localhost warning -->
          <div
            v-if="isLocalhost"
            class="flex items-start gap-3 rounded-lg bg-amber-50 p-3 ring-1 ring-amber-200 dark:bg-amber-900/20 dark:ring-amber-700/40"
          >
            <UIcon name="i-lucide-triangle-alert" class="mt-0.5 h-4 w-4 shrink-0 text-amber-600 dark:text-amber-400" />
            <p class="text-sm text-amber-800 dark:text-amber-300">
              Open the panel using the server&apos;s public IP to generate a valid proxy link.
            </p>
          </div>

          <!-- Config warning -->
          <div
            v-else-if="telegramProxy.warning"
            class="flex items-center gap-2 text-xs text-amber-600 dark:text-amber-400"
          >
            <UIcon name="i-lucide-triangle-alert" class="h-3.5 w-3.5 shrink-0" />
            {{ telegramProxy.warning }}
          </div>

          <!-- Link -->
          <div v-else class="flex items-center gap-2 rounded-lg bg-neutral-100 px-3 py-2 dark:bg-neutral-900">
            <code class="flex-1 break-all font-mono text-xs text-neutral-700 dark:text-neutral-300">{{ telegramProxy.link }}</code>
            <UButton
              icon="i-lucide-copy"
              color="neutral"
              variant="ghost"
              size="xs"
              class="shrink-0"
              @click="copyLink(telegramProxy.link!)"
            />
            <UButton
              :to="telegramProxy.link!"
              external
              icon="i-simple-icons-telegram"
              color="neutral"
              variant="ghost"
              size="xs"
              class="shrink-0"
            />
          </div>
        </UCard>

        <!-- Recent Logs -->
        <UCard>
          <template #header>
            <div class="flex items-center justify-between gap-2">
              <div class="flex items-center gap-2">
                <UIcon name="i-lucide-terminal" class="h-4 w-4 text-neutral-500" />
                <span class="text-sm font-semibold text-neutral-900 dark:text-white">Recent Logs</span>
                <span class="text-xs text-neutral-400">({{ filteredLogs.length }})</span>
              </div>
              <div class="flex items-center gap-3">
                <UInput v-model="logSearch" placeholder="Search logs…" icon="i-lucide-search" size="xs" class="w-40" />
                <UButton icon="i-lucide-maximize-2" size="xs" variant="ghost" color="neutral" @click="isLogFullscreen = true" />
                <label class="flex cursor-pointer select-none items-center gap-1.5">
                  <input type="checkbox" v-model="autoScroll" class="rounded accent-primary-500" />
                  <span class="text-xs text-neutral-500 dark:text-neutral-400">Auto-scroll</span>
                </label>
              </div>
            </div>
          </template>

          <div ref="logsContainer" class="h-72 overflow-y-auto rounded-lg bg-neutral-950 p-4 font-mono text-xs leading-relaxed">
            <div v-if="filteredLogs.length === 0" class="text-neutral-600">{{ logSearch ? 'No matching logs.' : 'No logs yet.' }}</div>
            <div v-for="(log, idx) in filteredLogs" :key="idx" class="text-neutral-400">
              {{ log }}
            </div>
          </div>
        </UCard>

        <!-- Log Fullscreen Modal -->
        <UModal v-model:open="isLogFullscreen" title="Logs" fullscreen>
          <template #default />
          <template #body>
            <div class="flex flex-col gap-3 h-full">
              <div class="flex items-center gap-3">
                <UInput v-model="logSearch" placeholder="Search logs…" icon="i-lucide-search" class="flex-1" />
                <span class="text-xs text-neutral-400 whitespace-nowrap">{{ filteredLogs.length }} lines</span>
              </div>
              <div ref="fullscreenLogsContainer" class="flex-1 min-h-0 overflow-y-auto rounded-lg bg-neutral-950 p-4 font-mono text-xs leading-relaxed" style="max-height: calc(100vh - 200px)">
                <div v-if="filteredLogs.length === 0" class="text-neutral-600">{{ logSearch ? 'No matching logs.' : 'No logs yet.' }}</div>
                <div v-for="(log, idx) in filteredLogs" :key="idx" class="text-neutral-400">
                  {{ log }}
                </div>
              </div>
            </div>
          </template>
        </UModal>
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
