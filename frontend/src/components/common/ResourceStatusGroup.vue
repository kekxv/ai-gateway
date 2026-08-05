<script setup lang="ts">
defineProps<{
  status: 'enabled' | 'disabled' | 'warning' | 'danger'
  title: string
  count: number
}>()
</script>

<template>
  <section
    class="resource-status-group"
    :class="`is-${status}`"
    :aria-label="`${title}资源`"
  >
    <header class="resource-status-group__header">
      <div class="resource-status-group__title">
        <span class="resource-status-group__dot" aria-hidden="true" />
        <h3>{{ title }}</h3>
      </div>
      <span class="resource-status-group__count">{{ count }} 个</span>
    </header>
    <div class="resource-status-group__content">
      <slot />
    </div>
  </section>
</template>

<style scoped>
.resource-status-group {
  border: 1px solid var(--gateway-border);
  border-radius: 12px;
  overflow: hidden;
}

.resource-status-group__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  min-height: 2.75rem;
  padding: 0.625rem 0.875rem;
  border-bottom: 1px solid var(--gateway-border);
}

.resource-status-group__title {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  min-width: 0;
}

.resource-status-group__title h3 {
  margin: 0;
  color: var(--gateway-text);
  font-size: 0.875rem;
  font-weight: 700;
}

.resource-status-group__dot {
  width: 0.5rem;
  height: 0.5rem;
  border-radius: 999px;
  flex: 0 0 auto;
}

.resource-status-group__count {
  color: var(--gateway-muted);
  font-size: 0.8125rem;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.resource-status-group__content {
  padding: 0.75rem;
}

.resource-status-group.is-enabled {
  border-color: #bbf7d0;
}

.resource-status-group.is-enabled .resource-status-group__header {
  background: #f0fdf4;
  border-bottom-color: #bbf7d0;
}

.resource-status-group.is-enabled .resource-status-group__dot {
  background: #16a34a;
  box-shadow: 0 0 0 3px #dcfce7;
}

.resource-status-group.is-disabled {
  border-color: #dbe4ee;
}

.resource-status-group.is-disabled .resource-status-group__header {
  background: #f8fafc;
  border-bottom-color: #dbe4ee;
}

.resource-status-group.is-disabled .resource-status-group__dot {
  background: #94a3b8;
  box-shadow: 0 0 0 3px #e2e8f0;
}

.resource-status-group.is-warning {
  border-color: #fde68a;
}

.resource-status-group.is-warning .resource-status-group__header {
  background: #fffbeb;
  border-bottom-color: #fde68a;
}

.resource-status-group.is-warning .resource-status-group__dot {
  background: #d97706;
  box-shadow: 0 0 0 3px #fef3c7;
}

.resource-status-group.is-danger {
  border-color: #fecdd3;
}

.resource-status-group.is-danger .resource-status-group__header {
  background: #fff1f2;
  border-bottom-color: #fecdd3;
}

.resource-status-group.is-danger .resource-status-group__dot {
  background: #e11d48;
  box-shadow: 0 0 0 3px #ffe4e6;
}

@media (max-width: 640px) {
  .resource-status-group__content {
    padding: 0.625rem;
  }
}
</style>
