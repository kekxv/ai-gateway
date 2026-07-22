<script setup lang="ts">
import { ElButton } from 'element-plus'
import 'element-plus/theme-chalk/el-button.css'
import { RouterLink } from 'vue-router'
</script>

<template>
  <main class="not-found">
    <section class="page-card not-found__card" aria-labelledby="not-found-title">
      <p class="not-found__code">404</p>
      <h1 id="not-found-title">页面不存在</h1>
      <p>无法找到你访问的页面，请检查地址或返回控制台。</p>
      <RouterLink to="/">
        <ElButton type="primary">返回控制台</ElButton>
      </RouterLink>
    </section>
  </main>
</template>

<style scoped>
.not-found {
  display: grid;
  min-height: 100vh;
  place-items: center;
  padding: 1rem;
}

.not-found__card {
  width: min(100%, 32rem);
  padding: 3rem 2rem;
  text-align: center;
}

.not-found__code {
  margin: 0;
  color: var(--gateway-brand);
  font-size: 4rem;
  font-weight: 800;
  line-height: 1;
}

h1 {
  margin: 1rem 0 0.75rem;
}

.not-found__card > p:not(.not-found__code) {
  margin: 0 0 1.5rem;
  color: var(--gateway-muted);
}
</style>
