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

const TokenUsageStats = () => {
  const { t } = useTranslation();
  const [stats, setStats] = useState<StatsData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    const fetchStats = async () => {
      setIsLoading(true);
      try {
        const response = await fetch('/api/users/me/stats', {
          headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` },
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error);
        setStats(data);
      } catch (err: any) {
        setError(err.message);
      } finally {
        setIsLoading(false);
      }
    };
    fetchStats();
  }, []);

  if (isLoading) {
    return <div>{t('common.loading', 'Loading...')}</div>;
  }

  if (error) {
    return <div className="text-red-600">{t('common.error', 'Error')}: {error}</div>;
  }

  if (!stats) {
    return <div>{t('profile.usage.noData', 'No usage data available.')}</div>;
  }

  const formattedDailyData = Object.entries(stats.dailyUsage).map(([date, totalTokens]) => ({
    date,
    tokens: totalTokens,
  }));

  return (
    <div className="space-y-8">
      <div>
        <h2 className="text-2xl font-bold">{t('profile.usage.title', 'Token Usage Statistics')}</h2>
        <p className="mt-1 text-sm text-gray-600 dark:text-gray-400">
          {t('profile.usage.description', 'Here is a summary of your token consumption.')}
        </p>
      </div>

      {/* Total Usage */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="p-4 bg-white dark:bg-gray-800 rounded-lg shadow">
          <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400">{t('profile.usage.total.prompt', 'Prompt Tokens')}</h3>
          <p className="mt-1 text-3xl font-semibold">{stats.totalUsage.promptTokens.toLocaleString()}</p>
        </div>
        <div className="p-4 bg-white dark:bg-gray-800 rounded-lg shadow">
          <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400">{t('profile.usage.total.completion', 'Completion Tokens')}</h3>
          <p className="mt-1 text-3xl font-semibold">{stats.totalUsage.completionTokens.toLocaleString()}</p>
        </div>
        <div className="p-4 bg-white dark:bg-gray-800 rounded-lg shadow">
          <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400">{t('profile.usage.total.total', 'Total Tokens')}</h3>
          <p className="mt-1 text-3xl font-semibold">{stats.totalUsage.totalTokens.toLocaleString()}</p>
        </div>
      </div>

      {/* Daily Usage Chart */}
      <div className="p-4 bg-white dark:bg-gray-800 rounded-lg shadow">
        <h3 className="text-lg font-semibold mb-4">{t('profile.usage.daily.title', 'Usage Last 30 Days')}</h3>
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
      <div className="p-4 bg-white dark:bg-gray-800 rounded-lg shadow">
        <h3 className="text-lg font-semibold mb-4">{t('profile.usage.byModel.title', 'Usage by Model')}</h3>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
            <thead className="bg-gray-50 dark:bg-gray-700">
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
  );
};

export default TokenUsageStats;
