'use client';

import { I18nextProvider } from 'react-i18next';
import { appWithTranslation } from 'next-i18next';
import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import common_zh from '../../public/locales/zh/common.json';
import common_en from '../../public/locales/en/common.json';

i18n
  .use(initReactI18next)
  .init({
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
  });

export default function I18nProvider({ children }: { children: React.ReactNode }) {
  return (
    <I18nextProvider i18n={i18n}>
      {children}
    </I18nextProvider>
  );
}