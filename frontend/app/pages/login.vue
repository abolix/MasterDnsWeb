<script setup lang="ts">
definePageMeta({
	layout: 'auth',
	title: 'Sign In'
})

const { login } = useAuth()
const router = useRouter()
const toast = useToast()

const state = reactive({
	username: '',
	password: ''
})

const isSubmitting = ref(false)
const colorMode = useColorMode()

const isDark = computed(() => colorMode.value === 'dark')

function toggleColorMode() {
	colorMode.preference = isDark.value ? 'light' : 'dark'
}

function validateForm(formState: typeof state) {
	const errors = []

	if (!formState.username) {
		errors.push({ name: 'username', message: 'Username is required.' })
	}

	if (!formState.password) {
		errors.push({ name: 'password', message: 'Password is required.' })
	}

	return errors
}

async function onSubmit() {
	try {
		isSubmitting.value = true
		await login(state.username, state.password)
		await router.push('/')
	}
	catch (error: any) {
		toast.add({
			title: 'Login failed',
			description: error?.data?.detail || 'Unable to sign in with the provided credentials.',
			icon: 'i-lucide-circle-alert',
			color: 'error'
		})
	}
	finally {
		isSubmitting.value = false
	}
}
</script>

<template>
	<div class="mx-auto flex min-h-screen w-full max-w-sm items-center px-6 py-10">
		<div class="w-full space-y-8">
			<!-- Branding -->
			<div class="text-center">
				<div class="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-linear-to-br from-primary-500 to-primary-600 shadow-lg shadow-primary-500/20">
					<UIcon name="i-lucide-shield" class="h-7 w-7 text-white" />
				</div>
				<h1 class="mt-4 text-2xl font-bold tracking-tight text-neutral-900 dark:text-white">MasterDNS</h1>
				<p class="mt-1 text-sm text-neutral-500 dark:text-neutral-400">Sign in to your admin panel</p>
			</div>

			<UCard>
				<UForm :state="state" :validate="validateForm" class="space-y-5" @submit="onSubmit">
					<UFormField name="username" label="Username" required>
						<UInput
							v-model="state.username"
							placeholder="admin"
							autocomplete="username"
							icon="i-lucide-mail"
							class="w-full"
						/>
					</UFormField>

					<UFormField name="password" label="Password" required>
						<UInput
							v-model="state.password"
							type="password"
							placeholder="••••••••"
							autocomplete="current-password"
							icon="i-lucide-lock"
							class="w-full"
						/>
					</UFormField>

					<UButton type="submit" block :loading="isSubmitting" size="lg">Sign In</UButton>
				</UForm>
			</UCard>

			<!-- Theme toggle -->
			<div class="flex justify-center">
				<UButton
					:icon="isDark ? 'i-lucide-sun' : 'i-lucide-moon'"
					color="neutral"
					variant="ghost"
					size="sm"
					aria-label="Toggle theme"
					@click="toggleColorMode"
				/>
			</div>
		</div>
	</div>
</template>
