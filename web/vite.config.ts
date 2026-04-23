import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

function isInPackages(id: string, packages: string[]) {
  return packages.some(pkg => id.includes(`/node_modules/${pkg}/`) || id.includes(`/node_modules/.pnpm/${pkg}@`))
}

export default defineConfig({
  plugins: [vue(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src')
    }
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return

          if (isInPackages(id, [
            'element-plus',
            '@element-plus/icons-vue',
            '@floating-ui',
            '@popperjs/core',
            '@ctrl/tinycolor',
            'async-validator',
            'dayjs',
            'escape-html',
            'lodash',
            'lodash-es',
            'lodash-unified',
            'memoize-one',
            'normalize-wheel-es'
          ])) {
            return 'vendor-ui'
          }

          if (isInPackages(id, [
            'vue',
            '@vue',
            'vue-router',
            'pinia',
            'vue-i18n',
            '@intlify',
            '@vueuse'
          ])) {
            return 'vendor-framework'
          }

          if (isInPackages(id, [
            'highlight.js',
            'katex',
            'marked',
            'marked-highlight',
            'dompurify',
            'mermaid'
          ])) {
            return 'vendor-md'
          }

          if (isInPackages(id, [
            'echarts'
          ])) {
            return 'vendor-chart-core'
          }

          if (isInPackages(id, [
            'zrender'
          ])) {
            return 'vendor-chart-renderer'
          }

          if (isInPackages(id, [
            'vue-echarts',
            'resize-detector'
          ])) {
            return 'vendor-chart-vue'
          }

          if (isInPackages(id, [
            'axios',
            'diff',
            'qrcode'
          ])) {
            return 'vendor-utils'
          }
        }
      }
    }
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:3000',
        changeOrigin: true
      }
    }
  },
  test: {
    globals: true,
    environment: 'jsdom',
    include: ['src/**/*.{test,spec}.{js,ts}'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'html'],
      exclude: [
        'node_modules/',
        'src/**/*.d.ts',
        'src/main.ts',
        'e2e/'
      ]
    }
  }
})
