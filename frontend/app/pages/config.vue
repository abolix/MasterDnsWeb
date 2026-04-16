<script setup lang="ts">
definePageMeta({
  title: 'Configuration'
})

const route = useRoute()
const toast = useToast()
const { instances, loadInstances, isLoading, updateInstanceConfig } = useMasterDns()

const instanceId = computed(() => route.query.instance as string)
const currentInstance = computed(() => {
  if (!instanceId.value) return null
  return instances.value.find(i => i.id === instanceId.value)
})

const tomlText = ref(currentInstance.value?.config_toml || '')
const resolverText = ref(currentInstance.value?.resolvers.join('\n') || '')
const isApplying = ref(false)
const tomlError = ref('')

watch(
  currentInstance,
  (newInstance) => {
    if (newInstance) {
      tomlText.value = newInstance.config_toml
      resolverText.value = newInstance.resolvers.join('\n')
      tomlError.value = ''
    }
  },
  { immediate: true }
)

onMounted(async () => {
  try {
    await loadInstances()
  }
  catch (error: any) {
    toast.add({
      title: 'Failed to load instance config',
      description: error?.data?.detail || 'Could not fetch instance data from backend.',
      icon: 'i-lucide-circle-alert',
      color: 'error',
    })
  }
})

function parseResolvers(text: string) {
  const seen = new Set<string>()

  return text
    .split(/\r?\n/)
    .map(line => line.trim())
    .filter((line) => line && !line.startsWith('#'))
    .filter((line) => {
      if (seen.has(line)) {
        return false
      }

      seen.add(line)
      return true
    })
}

function removeDuplicateResolvers() {
  const resolvers = parseResolvers(resolverText.value)
  resolverText.value = resolvers.join('\n')

  useToast().add({
    title: 'Resolvers cleaned',
    icon: 'i-lucide-list-filter',
    color: 'success',
  })
}

function stripTomlCommentFromLine(line: string) {
  let result = ''
  let inSingleQuote = false
  let inDoubleQuote = false

  for (let index = 0; index < line.length; index += 1) {
    const character = line[index]
    const previousCharacter = index > 0 ? line[index - 1] : ''

    if (character === '"' && previousCharacter !== '\\' && !inSingleQuote) {
      inDoubleQuote = !inDoubleQuote
    }
    else if (character === '\'' && previousCharacter !== '\\' && !inDoubleQuote) {
      inSingleQuote = !inSingleQuote
    }
    else if (character === '#' && !inSingleQuote && !inDoubleQuote) {
      break
    }

    result += character
  }

  return result.trimEnd()
}

function removeTomlComments() {
  tomlText.value = tomlText.value
    .split(/\r?\n/)
    .map(stripTomlCommentFromLine)
    .filter((line, index, lines) => line || (index > 0 && lines[index - 1]))
    .join('\n')

  useToast().add({
    title: 'Comments removed',
    description: 'TOML comments were removed from the configuration.',
    icon: 'i-lucide-eraser',
    color: 'success',
  })
}

function validateToml(toml: string): boolean {
  tomlError.value = ''

  if (!toml.trim()) {
    tomlError.value = 'Configuration cannot be empty'
    return false
  }

  if (!toml.split(/\r?\n/).some(line => line.includes('='))) {
    tomlError.value = 'Configuration must contain key/value lines (e.g., DOMAINS = ["example.com"])'
    return false
  }

  return true
}

async function applyConfig() {
  if (!currentInstance.value) return

  if (!validateToml(tomlText.value)) {
    return
  }

  const resolvers = parseResolvers(resolverText.value)

  if (resolvers.length === 0) {
    tomlError.value = 'Add at least one resolver before applying the configuration'
    return
  }

  isApplying.value = true

  try {
    await updateInstanceConfig(currentInstance.value.id, tomlText.value, resolvers)
    resolverText.value = resolvers.join('\n')

    toast.add({
      title: 'Configuration Applied',
      description: `Config saved for ${currentInstance.value.name}`,
      icon: 'i-lucide-check-circle',
      color: 'success',
    })
  }
  catch (error: any) {
    toast.add({
      title: 'Could not apply configuration',
      description: error?.data?.detail || error?.message || 'Backend rejected the configuration update.',
      icon: 'i-lucide-circle-alert',
      color: 'error',
    })
  }
  finally {
    isApplying.value = false
  }
}
</script>

<template>
  <div v-if="!instanceId" class="flex h-full items-center justify-center">
    <div class="text-center">
      <UIcon name="i-lucide-alert-circle" class="mx-auto h-12 w-12 text-neutral-400" />
      <p class="mt-4 text-sm font-medium text-neutral-600 dark:text-neutral-400">No instance selected</p>
    </div>
  </div>
  <div v-else-if="!currentInstance" class="flex h-full items-center justify-center">
    <div class="text-center">
      <UIcon name="i-lucide-loader-circle" class="mx-auto h-12 w-12 animate-spin text-neutral-400" />
      <p class="mt-4 text-sm font-medium text-neutral-600 dark:text-neutral-400">
        {{ isLoading ? 'Loading instance...' : 'Instance not found' }}
      </p>
    </div>
  </div>
  <div v-else class="space-y-8">
    <!-- Page Header & Apply Button -->
    <div class="flex items-center justify-between">
      <div>
        <UButton
          to="/instances"
          icon="i-lucide-arrow-left"
          color="neutral"
          variant="ghost"
          size="sm"
          class="-ml-2 mb-2"
        >
          Back to Instances
        </UButton>
        <h1 class="text-2xl font-bold tracking-tight text-neutral-900 dark:text-white">Configuration</h1>
        <p class="mt-1 text-sm text-neutral-500 dark:text-neutral-400">
          Editing <strong class="text-neutral-700 dark:text-neutral-200">{{ currentInstance.name }}</strong>
        </p>
      </div>
      <div class="flex gap-2">
        <UButton
          @click="applyConfig"
          :loading="isApplying"
          icon="i-lucide-rocket"
          size="md"
        >
          Apply & Restart
        </UButton>
      </div>
    </div>

    <div class="grid grid-cols-1 gap-6 lg:grid-cols-3">
      <div class="lg:col-span-2 space-y-4">
        <UCard>
          <template #header>
            <div class="flex items-center justify-between gap-3">
              <div class="flex items-center gap-2">
                <UIcon name="i-lucide-file-text" class="h-4 w-4 text-neutral-500" />
                <span class="text-sm font-semibold text-neutral-900 dark:text-white">Configuration (TOML)</span>
              </div>
              <UButton
                icon="i-lucide-eraser"
                color="neutral"
                variant="ghost"
                size="xs"
                @click="removeTomlComments"
              >
                Remove Comments
              </UButton>
            </div>
          </template>

          <!-- Validation Error -->
          <div v-if="tomlError" class="mb-4 rounded-lg bg-red-50 p-3 ring-1 ring-red-200 dark:bg-red-900/20 dark:ring-red-800/50">
            <div class="flex items-center gap-2">
              <UIcon name="i-lucide-alert-triangle" class="h-4 w-4 text-red-600 dark:text-red-400" />
              <p class="text-sm text-red-700 dark:text-red-300">{{ tomlError }}</p>
            </div>
          </div>

          <!-- TOML Textarea -->
          <textarea
            v-model="tomlText"
            class="w-full h-96 rounded-lg border-0 bg-neutral-950 p-4 font-mono text-sm text-neutral-100 placeholder-neutral-600 ring-1 ring-neutral-800 focus:ring-2 focus:ring-primary-500 resize-none"
            placeholder='DOMAINS = ["g.gfjz.cc"]&#10;PROTOCOL_TYPE = "SOCKS5"'
            spellcheck="false"
          />
        </UCard>
      </div>

      <div class="lg:col-span-1 space-y-4">
        <UCard>
          <template #header>
            <div class="flex items-center justify-between gap-3">
              <div>
                <div class="flex items-center gap-2">
                  <UIcon name="i-lucide-list-tree" class="h-4 w-4 text-neutral-500" />
                  <span class="text-sm font-semibold text-neutral-900 dark:text-white">Resolvers</span>
                </div>
                <p class="mt-1 text-xs text-neutral-500 dark:text-neutral-400">One resolver per line</p>
              </div>
              <div class="flex items-center gap-2">
                <UBadge color="neutral" variant="subtle">{{ parseResolvers(resolverText).length }}</UBadge>
                <UButton
                  icon="i-lucide-list-filter"
                  color="neutral"
                  variant="ghost"
                  size="xs"
                  @click="removeDuplicateResolvers"
                >
                  Remove duplicates
                </UButton>
              </div>
            </div>
          </template>

          <textarea
            v-model="resolverText"
            class="w-full h-96 rounded-lg border-0 bg-neutral-950 p-4 font-mono text-sm text-neutral-100 placeholder-neutral-600 ring-1 ring-neutral-800 focus:ring-2 focus:ring-primary-500 resize-none"
            placeholder="10.104.204.103&#10;10.104.205.119&#10;109.109.34.84"
            spellcheck="false"
          />
        </UCard>
      </div>
    </div>
  </div>
</template>
