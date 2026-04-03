import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import './styles/global.css'

import App from './App.vue'
import { router } from './router'
import { createI18n } from 'vue-i18n'

// Import locales
import zhLocale from '@/../public/locales/zh/common.json'
import enLocale from '@/../public/locales/en/common.json'

// Create i18n instance
const i18n = createI18n({
  legacy: false,
  locale: localStorage.getItem('locale') || 'zh',
  fallbackLocale: 'zh',
  messages: {
    zh: zhLocale,
    en: enLocale
  }
})

// Create app
const app = createApp(App)

// Use plugins
app.use(createPinia())
app.use(router)
app.use(ElementPlus)
app.use(i18n)

// Mount app
app.mount('#app')