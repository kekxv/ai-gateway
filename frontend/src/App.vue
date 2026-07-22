<template>
  <main data-testid="console-placeholder" class="console-placeholder">
    <section aria-labelledby="console-title" class="console-placeholder__card">
      <p class="console-placeholder__eyebrow">AI Gateway</p>
      <h1 id="console-title">AI Gateway 管理控制台</h1>
      <p>控制台界面正在建设中，请稍后访问。</p>
    </section>
  </main>
</template>

<style scoped>
.console-placeholder {
  display: grid;
  min-height: 100vh;
  place-items: center;
  padding: 2rem;
  color: #1f2937;
  background: #f5f7fa;
}

.console-placeholder__card {
  width: min(100%, 32rem);
  padding: 3rem;
  text-align: center;
  background: #ffffff;
  border: 1px solid #dcdfe6;
  border-radius: 0.75rem;
  box-shadow: 0 1rem 2.5rem rgb(31 41 55 / 8%);
}

.console-placeholder__eyebrow {
  margin: 0 0 0.75rem;
  color: #409eff;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

h1 {
  margin: 0 0 1rem;
  font-size: clamp(1.75rem, 5vw, 2.5rem);
}

p {
  margin: 0;
  line-height: 1.7;
}
</style>
