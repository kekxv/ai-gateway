<template>
  <div class="min-h-screen bg-gradient-to-br from-indigo-100 via-white to-purple-50 flex items-center justify-center p-4 relative overflow-hidden">
    <!-- 背景装饰 -->
    <div class="absolute inset-0 overflow-hidden pointer-events-none">
      <div class="absolute -top-40 -right-40 w-80 h-80 bg-indigo-200 rounded-full opacity-30 blur-3xl"></div>
      <div class="absolute -bottom-40 -left-40 w-80 h-80 bg-purple-200 rounded-full opacity-30 blur-3xl"></div>
      <div class="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-96 h-96 bg-blue-100 rounded-full opacity-20 blur-3xl"></div>
    </div>

    <!-- 登录卡片 -->
    <div class="relative w-full max-w-md animate-fadeIn">
      <div class="bg-white/80 backdrop-blur-sm rounded-2xl shadow-xl border border-gray-100 p-8">
        <slot />
      </div>

      <!-- 底部版权信息 -->
      <div class="text-center mt-6 text-gray-400 text-sm">
        AI Gateway &copy; {{ new Date().getFullYear() }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
// 美化后的认证布局组件
</script>

<style scoped>
@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.animate-fadeIn {
  animation: fadeIn 0.5s ease-out forwards;
}
</style>