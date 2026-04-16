<script setup lang="ts">
const { hasRestored, restoreSession } = useAuth()

onMounted(() => {
  if (!hasRestored.value) {
    void restoreSession()
  }
})
</script>

<template>
  <UApp>
    <NuxtLoadingIndicator/>
    <NuxtLayout>
      <NuxtPage/>
    </NuxtLayout>
  </UApp>
</template>


<style>
@reference "~/assets/css/main.css";

* {
  font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
}
</style>
