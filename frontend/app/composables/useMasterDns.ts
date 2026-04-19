export interface InstanceMetrics {
  cpu: number
  memory: number
  uptime_seconds: number
}

export interface Instance {
  id: string
  name: string
  status: 'running' | 'stopped'
  metrics?: InstanceMetrics
  logs: string[]
  config_toml: string
  resolvers: string[]
}

export interface HostMetrics {
  cpu: number
  memory: number
  disk_used_percent: number
  timestamp: string
}

interface BackendProfileListResponse {
  status: string
  count: number
  profiles: string[]
}

interface BackendProfileResponse {
  status: string
  data: {
    name: string
    configure: Record<string, unknown>
    resolver: string[]
  }
}

interface BackendProfileUpsertRequest {
  configure: Record<string, unknown>
  resolver: string[]
}

// Keys that must appear first in serialized TOML output
const PRIORITY_KEYS = ['DOMAINS', 'ENCRYPTION_KEY'] as const

const DEFAULT_CONFIG_OBJECT: Record<string, unknown> = {
  DOMAINS: ['example.com'],
  DATA_ENCRYPTION_METHOD: 1,
  ENCRYPTION_KEY: 'encryption_key_here',
  PROTOCOL_TYPE: 'SOCKS5',
  LISTEN_IP: '0.0.0.0',
  LISTEN_PORT: 18000,
  SOCKS5_AUTH: false,
  RESOLVER_BALANCING_STRATEGY: 6,
  PACKET_DUPLICATION_COUNT: 4,
  SETUP_PACKET_DUPLICATION_COUNT: 5,
  MIN_UPLOAD_MTU: 38,
  MIN_DOWNLOAD_MTU: 700,
  MAX_UPLOAD_MTU: 150,
  MAX_DOWNLOAD_MTU: 950,
  RX_TX_WORKERS: 64,
  TUNNEL_PROCESS_WORKERS: 64,
  SESSION_INIT_RACING_COUNT: 3,
  MAX_PACKETS_PER_BATCH: 20,
  ARQ_WINDOW_SIZE: 6000,
  ARQ_INITIAL_RTO_SECONDS: 0.2,
  ARQ_MAX_RTO_SECONDS: 1.0,
  LOG_LEVEL: 'INFO',
}

function deepCloneConfig(config: Record<string, unknown>) {
  return JSON.parse(JSON.stringify(config)) as Record<string, unknown>
}

function stringifyTomlValue(value: unknown) {
  if (Array.isArray(value)) {
    return JSON.stringify(value)
  }

  if (typeof value === 'string') {
    return JSON.stringify(value)
  }

  if (typeof value === 'boolean') {
    return value ? 'true' : 'false'
  }

  return String(value)
}

function configObjectToToml(config: Record<string, unknown>) {
  const keys = Object.keys(config)
  const orderedKeys = [
    ...PRIORITY_KEYS.filter(k => k in config),
    ...keys.filter(k => !(PRIORITY_KEYS as readonly string[]).includes(k)),
  ]
  return orderedKeys
    .map(key => `${key} = ${stringifyTomlValue(config[key])}`)
    .join('\n')
}

function stripInlineComment(line: string) {
  let inSingleQuote = false
  let inDoubleQuote = false

  for (let index = 0; index < line.length; index += 1) {
    const character = line[index]
    const previous = index > 0 ? line[index - 1] : ''

    if (character === '"' && previous !== '\\' && !inSingleQuote) {
      inDoubleQuote = !inDoubleQuote
      continue
    }

    if (character === '\'' && previous !== '\\' && !inDoubleQuote) {
      inSingleQuote = !inSingleQuote
      continue
    }

    if (character === '#' && !inSingleQuote && !inDoubleQuote) {
      return line.slice(0, index)
    }
  }

  return line
}

function parseTomlValue(rawValue: string): unknown {
  const cleaned = rawValue.trim()

  // Array
  if (cleaned.startsWith('[')) {
    try {
      return JSON.parse(cleaned)
    }
    catch {
      return cleaned
    }
  }

  // Boolean
  if (cleaned === 'true') return true
  if (cleaned === 'false') return false

  // Double-quoted string
  if (cleaned.startsWith('"') && cleaned.endsWith('"')) {
    try { return JSON.parse(cleaned) }
    catch { return cleaned.slice(1, -1) }
  }

  // Single-quoted string
  if (cleaned.startsWith('\'') && cleaned.endsWith('\'')) {
    return cleaned.slice(1, -1)
  }

  // Integer (no dot, no exponent with dot)
  if (/^-?\d+$/.test(cleaned)) {
    return Number.parseInt(cleaned, 10)
  }

  // Float
  if (/^-?\d*\.\d+([eE][+-]?\d+)?$/.test(cleaned) || /^-?\d+[eE][+-]?\d+$/.test(cleaned)) {
    return Number.parseFloat(cleaned)
  }

  return cleaned
}

function tomlToConfigObject(toml: string): Record<string, unknown> {
  const result: Record<string, unknown> = {}

  for (const rawLine of toml.split(/\r?\n/)) {
    const line = stripInlineComment(rawLine).trim()
    if (!line || !line.includes('=')) {
      continue
    }

    const separatorIndex = line.indexOf('=')
    const key = line.slice(0, separatorIndex).trim()
    const rawValue = line.slice(separatorIndex + 1).trim()

    if (!key) continue

    result[key] = parseTomlValue(rawValue)
  }

  return result
}

const DEFAULT_CONFIG_TOML = configObjectToToml(DEFAULT_CONFIG_OBJECT)

const DEFAULT_RESOLVERS = [
  '10.104.204.103',
  '10.104.205.119',
  '109.109.34.84',
  '128.65.176.139',
  '178.252.170.218',
  '185.120.220.29',
  '188.121.102.196',
  '217.219.120.82',
  '37.148.50.202',
  '46.245.90.90',
  '80.210.48.145',
  '94.182.193.14'
]

function normalizeInstanceName(name: string) {
  const normalized = name
    .trim()
    .replace(/\s+/g, '-')
    .replace(/[^A-Za-z0-9_-]/g, '')

  if (!normalized) {
    throw new Error('Instance name can only contain letters, numbers, hyphens, and underscores')
  }

  return normalized
}

export const useMasterDns = () => {
  const config = useRuntimeConfig()
  const instances = useState<Instance[]>('dns.instances', () => [])
  const isLoading = useState('dns.isLoading', () => false)
  const hasLoaded = useState('dns.hasLoaded', () => false)

  const hostMetrics = useState('dns.hostMetrics', () => ({
    cpu: 0,
    memory: 0,
    disk_used_percent: 0,
    timestamp: new Date().toISOString()
  }))

  const selectedInstanceId = useState('dns.selectedInstanceId', () => instances.value[0]?.id || null)

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

  const fetchOptions = {
    baseURL: apiBase,
    credentials: 'include' as const,
  }

  const loadInstances = async (force = false) => {
    if (isLoading.value || (hasLoaded.value && !force)) {
      return
    }

    isLoading.value = true

    try {
      const listResponse = await $fetch<BackendProfileListResponse>('/config', {
        ...fetchOptions,
        method: 'GET',
      })

      const details = await Promise.all(
        listResponse.profiles.map(async (profileName) => {
          return $fetch<BackendProfileResponse>(`/config/${encodeURIComponent(profileName)}`, {
            ...fetchOptions,
            method: 'GET',
          })
        })
      )

      const existingById = new Map(instances.value.map(instance => [instance.id, instance]))

      instances.value = details.map(({ data }) => {
        const existing = existingById.get(data.name)
        const configure = (data.configure || {}) as Record<string, unknown>
        const resolvers = (data.resolver || []).map(item => String(item))

        return {
          id: data.name,
          name: data.name,
          status: existing?.status || 'stopped',
          metrics: existing?.metrics,
          logs: existing?.logs || [
            `[${new Date().toISOString()}] Profile loaded from backend`,
          ],
          config_toml: configObjectToToml(configure as Record<string, unknown>),
          resolvers,
        }
      })

      if (!instances.value.find(instance => instance.id === selectedInstanceId.value)) {
        selectedInstanceId.value = instances.value[0]?.id || null
      }

      hasLoaded.value = true

      // Fetch real service status for each instance (non-blocking)
      for (const inst of instances.value) {
        fetchInstanceStatus(inst.id).catch(() => {})
      }
    }
    finally {
      isLoading.value = false
    }
  }

  const getInstanceById = (id: string) => instances.value.find(i => i.id === id)

  const getSelectedInstance = () => {
    if (!selectedInstanceId.value) return null
    return getInstanceById(selectedInstanceId.value)
  }

  const createInstance = async (name: string) => {
    const normalizedName = normalizeInstanceName(name)

    const requestBody = {
      name: normalizedName,
      configure: deepCloneConfig(DEFAULT_CONFIG_OBJECT),
      resolver: [...DEFAULT_RESOLVERS],
    }

    await $fetch('/config', {
      ...fetchOptions,
      method: 'POST',
      body: requestBody,
    })

    const newInstance: Instance = {
      id: normalizedName,
      name: normalizedName,
      status: 'stopped',
      logs: [
        `[${new Date().toISOString()}] Profile created`,
      ],
      config_toml: configObjectToToml(deepCloneConfig(DEFAULT_CONFIG_OBJECT)),
      resolvers: [...DEFAULT_RESOLVERS],
    }
    instances.value.push(newInstance)
    selectedInstanceId.value = normalizedName
    return newInstance
  }

  const deleteInstance = async (id: string) => {
    await $fetch(`/config/${encodeURIComponent(id)}`, {
      ...fetchOptions,
      method: 'DELETE',
    })

    const index = instances.value.findIndex(i => i.id === id)
    if (index !== -1) {
      instances.value.splice(index, 1)
      if (selectedInstanceId.value === id) {
        selectedInstanceId.value = instances.value[0]?.id || null
      }
    }
  }

  const startInstance = async (id: string) => {
    await $fetch(`/service/${encodeURIComponent(id)}/start`, {
      ...fetchOptions,
      method: 'POST',
    })
    const instance = getInstanceById(id)
    if (instance) {
      instance.status = 'running'
      instance.logs.push(`[${new Date().toISOString()}] Service started`)
      if (instance.logs.length > 50) instance.logs.shift()
    }
  }

  const stopInstance = async (id: string) => {
    await $fetch(`/service/${encodeURIComponent(id)}/stop`, {
      ...fetchOptions,
      method: 'POST',
    })
    const instance = getInstanceById(id)
    if (instance) {
      instance.status = 'stopped'
      instance.logs.push(`[${new Date().toISOString()}] Service stopped`)
      if (instance.logs.length > 50) instance.logs.shift()
    }
  }

  const restartInstance = async (id: string) => {
    await $fetch(`/service/${encodeURIComponent(id)}/restart`, {
      ...fetchOptions,
      method: 'POST',
    })
    const instance = getInstanceById(id)
    if (instance) {
      instance.status = 'running'
      instance.logs.push(`[${new Date().toISOString()}] Service restarted`)
      if (instance.logs.length > 50) instance.logs.shift()
    }
  }

  const fetchInstanceStatus = async (id: string) => {
    try {
      const result = await $fetch<{ status: string; return_code: number; enabled: string; output: string }>(`/service/${encodeURIComponent(id)}/status`, {
        ...fetchOptions,
        method: 'GET',
      })
      const instance = getInstanceById(id)
      if (instance) {
        instance.status = result.return_code === 0 ? 'running' : 'stopped'
      }
      return result
    }
    catch {
      // Service unit may not exist yet (e.g. on Windows dev), treat as stopped
      const instance = getInstanceById(id)
      if (instance) instance.status = 'stopped'
      return null
    }
  }

  const fetchInstanceLogs = async (id: string, lines: number = 100) => {
    try {
      const result = await $fetch<{ output: string }>(`/service/${encodeURIComponent(id)}/logs`, {
        ...fetchOptions,
        method: 'GET',
        params: { lines },
      })
      const instance = getInstanceById(id)
      if (instance && result.output) {
        instance.logs = result.output.split('\n').filter(Boolean)
      }
      return result
    }
    catch {
      return null
    }
  }

  const updateInstanceConfig = async (id: string, toml: string, resolvers: string[]) => {
    const instance = getInstanceById(id)
    const configure = tomlToConfigObject(toml)

    const payload: BackendProfileUpsertRequest = {
      configure,
      resolver: resolvers,
    }

    const response = await $fetch<{ service?: { start_warning?: string } }>(`/config/${encodeURIComponent(id)}`, {
      ...fetchOptions,
      method: 'PUT',
      body: payload,
    })

    if (instance) {
      instance.config_toml = configObjectToToml(configure)
      instance.resolvers = [...resolvers]
      instance.logs.push(`[${new Date().toISOString()}] Configuration updated on backend`)
      if (instance.logs.length > 50) {
        instance.logs.shift()
      }
    }

    // Backend does stop+start after config update; refresh the actual status
    await fetchInstanceStatus(id).catch(() => {})

    // Return any non-fatal warning from the backend (e.g. service failed to restart)
    return response?.service?.start_warning ?? null
  }

  const updateHostMetrics = async () => {
    try {
      const stats = await $fetch<{
        cpu_usage_percent: number
        memory: { usage_percent: number }
        disk: { usage_percent: number }
        collected_at: string
      }>('/system-stats', {
        ...fetchOptions,
        method: 'GET',
      })

      hostMetrics.value = {
        cpu: stats.cpu_usage_percent,
        memory: stats.memory.usage_percent,
        disk_used_percent: stats.disk.usage_percent,
        timestamp: stats.collected_at,
      }
    }
    catch {
      // Keep previous values if backend is unreachable
    }
  }

  const getInstanceLogs = (id: string, count: number = 50) => {
    const instance = getInstanceById(id)
    if (!instance) return []
    return instance.logs.slice(-count)
  }

  const binaryVersion = useState<string | null>('dns.binaryVersion', () => null)

  const fetchBinaryVersion = async () => {
    try {
      const result = await $fetch<{ version: string | null }>('/service/binary-version', {
        ...fetchOptions,
        method: 'GET',
      })
      binaryVersion.value = result.version ?? null
    }
    catch {
      binaryVersion.value = null
    }
  }

  if (import.meta.client && !hasLoaded.value && !isLoading.value) {
    void loadInstances()
  }

  return {
    instances: readonly(instances),
    hostMetrics: readonly(hostMetrics),
    isLoading: readonly(isLoading),
    hasLoaded: readonly(hasLoaded),
    selectedInstanceId,
    binaryVersion: readonly(binaryVersion),
    loadInstances,
    getInstanceById,
    getSelectedInstance,
    createInstance,
    deleteInstance,
    startInstance,
    stopInstance,
    restartInstance,
    fetchInstanceStatus,
    fetchInstanceLogs,
    updateInstanceConfig,
    updateHostMetrics,
    getInstanceLogs,
    fetchBinaryVersion,
  }
}
