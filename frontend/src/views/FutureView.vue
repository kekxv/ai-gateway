<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

import PageHeader from '@/components/common/PageHeader.vue'

const route = useRoute()
const title = computed(() =>
  typeof route.meta.title === 'string' ? route.meta.title : '管理页面',
)
</script>

<template>
  <PageHeader :title="title" description="该页面将在后续开发任务中提供。" />
  <section class="page-card future-view" aria-live="polite">
    <p>功能正在建设中。</p>
  </section>
</template>

<style scoped>
.future-view {
  display: grid;
  min-height: 16rem;
  place-items: center;
  padding: 2rem;
  color: var(--gateway-muted);
}

p {
  margin: 0;
}
</style>
