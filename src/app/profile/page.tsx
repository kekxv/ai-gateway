'use client';

import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import dynamic from 'next/dynamic';
import SecuritySettings from '@/components/SecuritySettings';

// Dynamically import the TokenUsageStats component to avoid SSR issues with recharts
const TokenUsageStats = dynamic(() => import('@/components/TokenUsageStats'), {
  ssr: false,
  loading: () => <p>Loading stats...</p>,
});

const ProfilePage = () => {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState('security');

  return (
    <div className="min-h-screen bg-gray-100 dark:bg-gray-900 text-gray-900 dark:text-gray-100">
      <main className="max-w-4xl mx-auto p-4 sm:p-6 lg:p-8">
        <div className="mb-8">
          <h1 className="text-3xl font-bold tracking-tight">{t('profile.title', 'User Profile')}</h1>
          <p className="text-lg text-gray-600 dark:text-gray-400">{t('profile.subtitle', 'Manage your account settings and track your usage.')}</p>
        </div>

        <div className="mb-6 border-b border-gray-200 dark:border-gray-700">
          <nav className="-mb-px flex space-x-6" aria-label="Tabs">
            <button
              onClick={() => setActiveTab('security')}
              className={`${ activeTab === 'security'
                  ? 'border-blue-500 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
              } whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm`}
            >
              {t('profile.tabs.security', 'Security')}
            </button>
            <button
              onClick={() => setActiveTab('usage')}
              className={`${ activeTab === 'usage'
                  ? 'border-blue-500 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
              } whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm`}
            >
              {t('profile.tabs.usage', 'Token Usage')}
            </button>
          </nav>
        </div>

        <div>
          {activeTab === 'security' && <SecuritySettings />}
          {activeTab === 'usage' && <TokenUsageStats />}
        </div>
      </main>
    </div>
  );
};

export default ProfilePage;