'use client';

import { useTranslation } from 'react-i18next';

import ChangePasswordForm from '@/components/ChangePasswordForm';
import TotpManager from '@/components/TotpManager';


const SecuritySettings = () => {
  const { t } = useTranslation();

  return (
    <div className="space-y-8">
      <div>
        <h2 className="text-2xl font-bold">{t('profile.security.title', 'Security Settings')}</h2>
        <p className="mt-1 text-sm text-gray-600 dark:text-gray-400">
          {t('profile.security.description', 'Manage your password and two-factor authentication.')}
        </p>
      </div>
      
      <div className="space-y-6">
        <ChangePasswordForm />
        <TotpManager />
      </div>
    </div>
  );
};

export default SecuritySettings;
