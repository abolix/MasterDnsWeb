<template>
  <main class="relative min-h-screen overflow-hidden bg-linear-to-br from-neutral-50 via-white to-neutral-100 dark:from-neutral-950 dark:via-neutral-900 dark:to-neutral-950">
    <!-- Decorative blobs -->
    <div class="pointer-events-none absolute inset-0">
      <div class="absolute -top-24 -left-24 h-96 w-96 rounded-full bg-primary-500/10 blur-3xl dark:bg-primary-500/5" />
      <div class="absolute -right-24 -bottom-24 h-96 w-96 rounded-full bg-violet-500/10 blur-3xl dark:bg-violet-500/5" />
    </div>
    <div class="relative z-10">
      <slot />
    </div>
  </main>
</template>
