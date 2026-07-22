<script setup lang="ts">
defineProps<{
  title: string
  description?: string
}>()
</script>

<template>
  <header class="page-header">
    <div>
      <h1 tabindex="-1">{{ title }}</h1>
      <p v-if="description">{{ description }}</p>
    </div>
    <div v-if="$slots.actions" class="page-header__actions">
      <slot name="actions" />
    </div>
  </header>
</template>

<style scoped>
.page-header {
  display: flex;
  gap: 1rem;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 1.25rem;
}

h1 {
  margin: 0;
  font-size: clamp(1.5rem, 3vw, 2rem);
  line-height: 1.25;
}

p {
  margin: 0.45rem 0 0;
  color: var(--gateway-muted);
  line-height: 1.6;
}

.page-header__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
  justify-content: flex-end;
}

@media (max-width: 640px) {
  .page-header {
    flex-direction: column;
  }

  .page-header__actions {
    width: 100%;
    justify-content: flex-start;
  }
}
</style>
