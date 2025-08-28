import { createInstance } from 'i18next';
import { initReactI18next } from 'react-i18next';
import common_zh from '../../public/locales/zh/common.json';
import common_en from '../../public/locales/en/common.json';

const i18n = createInstance({
  resources: {
    zh: {
      common: common_zh
    },
    en: {
      common: common_en
    }
  },
  fallbackLng: 'zh',
  debug: false,
  interpolation: {
    escapeValue: false,
  },
  defaultNS: 'common',
  lng: 'zh', // Set default language
});

i18n.use(initReactI18next).init();

export default i18n;