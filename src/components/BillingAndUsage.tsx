'use client';

import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, LineChart, Line } from 'recharts';

interface TotalUsage {
  promptTokens: number;
  completionTokens: number;
  totalTokens: number;
}

interface DailyUsage {
  [date: string]: number;
}

interface ModelUsage {
  modelName: string;
  totalTokens: number;
}

interface StatsData {
  totalUsage: TotalUsage;
  dailyUsage: DailyUsage;
  usageByModel: ModelUsage[];
}

const BillingAndUsage = () => {
  const { t } = useTranslation();
  const [userBalance, setUserBalance] = useState<number | null>(null);
  const [loadingBalance, setLoadingBalance] = useState(true);
  const [balanceError, setBalanceError] = useState<string | null>(null);
  
  const [stats, setStats] = useState<StatsData | null>(null);
  const [isLoadingStats, setIsLoadingStats] = useState(true);
  const [statsError, setStatsError] = useState('');

  useEffect(() => {
    // Fetch user balance
    const fetchUserBalance = async () => {
      setLoadingBalance(true);
      try {
        const token = localStorage.getItem('token');
        if (!token) {
          // Handle unauthenticated state, e.g., redirect to login
          return;
        }
        const response = await fetch('/api/users/me', {
          headers: {
            'Authorization': `Bearer ${token}`,
          },
        });
        if (!response.ok) {
          const errorData = await response.json();
          throw new Error(errorData.error || 'Failed to fetch user data');
        }
        const userData = await response.json();
        setUserBalance(userData.balance);
      } catch (err) {
        setBalanceError(err instanceof Error ? err.message : 'An unknown error occurred');
      } finally {
        setLoadingBalance(false);
      }
    };

    // Fetch token usage stats
    const fetchStats = async () => {
      setIsLoadingStats(true);
      try {
        const response = await fetch('/api/users/me/stats', {
          headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` },
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error);
        setStats(data);
      } catch (err: any) {
        setStatsError(err.message);
      } finally {
        setIsLoadingStats(false);
      }
    };

    fetchUserBalance();
    fetchStats();
  }, []);

  const formattedDailyData = stats ? Object.entries(stats.dailyUsage).map(([date, totalTokens]) => ({
    date,
    tokens: totalTokens,
  })) : [];

  return (
    <div className="space-y-8">
      <div>
        <h2 className="text-2xl font-bold">{t('profile.billingAndUsage.title', 'Billing and Usage')}</h2>
        <p className="mt-1 text-sm text-gray-600 dark:text-gray-400">
          {t('profile.billingAndUsage.description', 'Manage your billing information and track your token usage.')}
        </p>
      </div>

      {/* Billing Information */}
      <div className="bg-white dark:bg-gray-800 shadow-sm rounded-xl p-6">
        <h3 className="text-xl font-semibold text-gray-900 dark:text-gray-100 mb-4">{t('profile.billing.title', 'Billing Information')}</h3>
        {loadingBalance ? (
          <p>{t('common.loading')}</p>
        ) : balanceError ? (
          <p className="text-red-500">{t('common.error')}: {balanceError}</p>
        ) : (
          <div className="flex items-center justify-between p-4 bg-gray-50 dark:bg-gray-700 rounded-lg">
            <p className="text-lg font-medium text-gray-700 dark:text-gray-300">{t('profile.billing.currentBalance', 'Current Balance')}:</p>
            <p className="text-2xl font-bold text-indigo-600 dark:text-indigo-400">¥{((userBalance||0) / 10000).toFixed(4)}</p>
          </div>
        )}
      </div>

      {/* Token Usage Statistics */}
      <div className="bg-white dark:bg-gray-800 shadow-sm rounded-xl p-6">
        <h3 className="text-xl font-semibold text-gray-900 dark:text-gray-100 mb-4">{t('profile.usage.title', 'Token Usage Statistics')}</h3>
        
        {isLoadingStats ? (
          <p>{t('common.loading', 'Loading...')}</p>
        ) : statsError ? (
          <p className="text-red-600">{t('common.error', 'Error')}: {statsError}</p>
        ) : !stats ? (
          <p>{t('profile.usage.noData', 'No usage data available.')}</p>
        ) : (
          <div className="space-y-8">
            {/* Total Usage */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="p-4 bg-gray-50 dark:bg-gray-700 rounded-lg">
                <h4 className="text-sm font-medium text-gray-500 dark:text-gray-400">{t('profile.usage.total.prompt', 'Prompt Tokens')}</h4>
                <p className="mt-1 text-3xl font-semibold">{stats.totalUsage.promptTokens.toLocaleString()}</p>
              </div>
              <div className="p-4 bg-gray-50 dark:bg-gray-700 rounded-lg">
                <h4 className="text-sm font-medium text-gray-500 dark:text-gray-400">{t('profile.usage.total.completion', 'Completion Tokens')}</h4>
                <p className="mt-1 text-3xl font-semibold">{stats.totalUsage.completionTokens.toLocaleString()}</p>
              </div>
              <div className="p-4 bg-gray-50 dark:bg-gray-700 rounded-lg">
                <h4 className="text-sm font-medium text-gray-500 dark:text-gray-400">{t('profile.usage.total.total', 'Total Tokens')}</h4>
                <p className="mt-1 text-3xl font-semibold">{stats.totalUsage.totalTokens.toLocaleString()}</p>
              </div>
            </div>

            {/* Daily Usage Chart */}
            <div className="p-4 bg-gray-50 dark:bg-gray-700 rounded-lg">
              <h4 className="text-lg font-semibold mb-4">{t('profile.usage.daily.title', 'Usage Last 30 Days')}</h4>
              {formattedDailyData.length > 0 ? (
                <ResponsiveContainer width="100%" height={300}>
                  <LineChart data={formattedDailyData}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="date" />
                    <YAxis />
                    <Tooltip />
                    <Legend />
                    <Line type="monotone" dataKey="tokens" stroke="#8884d8" activeDot={{ r: 8 }} />
                  </LineChart>
                </ResponsiveContainer>
              ) : (
                <p className="text-center text-gray-500 py-10">{t('profile.usage.daily.noData', 'No usage data for the last 30 days.')}</p>
              )}
            </div>

            {/* Usage by Model */}
            <div className="p-4 bg-gray-50 dark:bg-gray-700 rounded-lg">
              <h4 className="text-lg font-semibold mb-4">{t('profile.usage.byModel.title', 'Usage by Model')}</h4>
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                  <thead className="bg-gray-100 dark:bg-gray-600">
                    <tr>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">{t('profile.usage.byModel.model', 'Model')}</th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">{t('profile.usage.byModel.tokens', 'Total Tokens')}</th>
                    </tr>
                  </thead>
                  <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
                    {stats.usageByModel.map((model) => (
                      <tr key={model.modelName}>
                        <td className="px-6 py-4 whitespace-nowrap text-sm font-medium">{model.modelName}</td>
                        <td className="px-6 py-4 whitespace-nowrap text-sm">{model.totalTokens.toLocaleString()}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default BillingAndUsage;