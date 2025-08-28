'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { useTranslation } from 'react-i18next';

type StatsData = {
  byProvider: Record<string, { totalTokens: number; promptTokens: number; completionTokens: number; requestCount: number }>;
  byChannel: Record<string, { totalTokens: number; promptTokens: number; completionTokens: number; requestCount: number }>;
  byModel: Record<string, { totalTokens: number; promptTokens: number; completionTokens: number; requestCount: number }>;
  byApiKey: Record<string, { totalTokens: number; promptTokens: number; completionTokens: number; requestCount: number }>;
  dailyUsage: { date: string; totalTokens: number; requestCount: number }[];
  weeklyUsage: { date: string; totalTokens: number; requestCount: number }[];
  monthlyUsage: { date: string; totalTokens: number; requestCount: number }[];
  userStats?: { total: number; active: number; disabled: number; expired: number };
  tokenUsageOverTime: { date: string; totalTokens: number; promptTokens: number; completionTokens: number; requestCount: number }[];
  userTokenUsageOverTime: { userName: string; data: { date: string; totalTokens: number; promptTokens: number; completionTokens: number; requestCount: number }[] }[];
  byUser?: Record<string, { totalTokens: number; promptTokens: number; completionTokens: number; requestCount: number }>;
};

const StatCard = ({ title, value, icon, color }: { title: string; value: string | number; icon: React.ReactNode; color?: string }) => (
  <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-100 hover:shadow-md transition-shadow duration-300">
    <div className="flex items-center space-x-4">
      <div className={`p-3 rounded-lg ${color || 'bg-indigo-100'}`}>
        {icon}
      </div>
      <div>
        <p className="text-sm text-gray-500">{title}</p>
        <p className="text-2xl font-bold text-gray-800">{value}</p>
      </div>
    </div>
  </div>
);

// Custom tooltip for charts
const CustomTooltip = ({ active, payload, label }: any) => {
  if (active && payload && payload.length) {
    return (
      <div className="bg-white p-4 border border-gray-200 shadow-lg rounded-lg">
        <p className="font-bold text-gray-800">{label}</p>
        {payload.map((entry: any, index: number) => (
          <p key={index} className="text-sm" style={{ color: entry.color }}>
            {entry.name}: {entry.value.toLocaleString()}
          </p>
        ))}
      </div>
    );
  }
  return null;
};

export default function DashboardPage() {
  const [stats, setStats] = useState<StatsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();
  const { t } = useTranslation('common');

  useEffect(() => {
    async function fetchStats() {
      try {
        const token = localStorage.getItem('token');
        const response = await fetch('/api/stats', {
          headers: {
            'Authorization': `Bearer ${token}`,
          },
        });
        if (response.status === 401) {
          router.push('/login');
          return;
        }
        if (!response.ok) {
          throw new Error('Failed to fetch stats');
        }
        const data = await response.json();
        setStats(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'An unknown error occurred');
      } finally {
        setLoading(false);
      }
    }

    fetchStats();
  }, []);

  if (loading) {
    return (
      <main className="container mx-auto p-8">
        <div className="flex justify-center items-center h-64">
          <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-indigo-500"></div>
        </div>
      </main>
    );
  }

  if (error) {
    return (
      <main className="container mx-auto p-8">
        <div className="bg-red-50 border border-red-200 rounded-lg p-6 text-center">
          <p className="text-red-700 font-medium">Error: {error}</p>
        </div>
      </main>
    );
  }

  if (!stats) {
    return (
      <main className="container mx-auto p-8">
        <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-6 text-center">
          <p className="text-yellow-700 font-medium">No stats available.</p>
        </div>
      </main>
    );
  }

  const totalRequests = Object.values(stats.byProvider).reduce((acc, provider) => acc + provider.requestCount, 0);
  const totalTokens = Object.values(stats.byProvider).reduce((acc, provider) => acc + provider.totalTokens, 0);
  const totalProviders = Object.keys(stats.byProvider).length;
  const totalModels = Object.keys(stats.byModel).length;

  // Colors for user lines in charts
  const CHART_COLORS = ['#6366f1', '#8b5cf6', '#ec4899', '#f43f5e', '#f59e0b', '#10b981', '#0ea5e9', '#8b5cf6'];

  const renderChart = (title: string, data: any[], xKey: string, yKey: string, yLabel: string, color: string = '#6366f1') => (
    <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-100">
      <h2 className="text-xl font-semibold text-gray-800 mb-4">{title}</h2>
      <ResponsiveContainer width="100%" height={300}>
        <LineChart data={data} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
          <XAxis 
            dataKey={xKey} 
            stroke="#6b7280"
            tick={{ fontSize: 12 }}
          />
          <YAxis 
            stroke="#6b7280"
            tick={{ fontSize: 12 }}
          />
          <Tooltip content={<CustomTooltip />} />
          <Legend />
          <Line 
            type="monotone" 
            dataKey={yKey} 
            stroke={color} 
            name={yLabel} 
            strokeWidth={2}
            dot={{ r: 3 }}
            activeDot={{ r: 6 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );

  // Render chart with multiple lines for different users
  const renderMultiUserChart = (title: string, userData: { userName: string; data: { date: string; totalTokens: number; promptTokens: number; completionTokens: number; requestCount: number }[] }[]) => {
    // Transform data for the chart
    const chartData: any[] = [];
    
    // Get all unique dates
    const allDates = new Set<string>();
    userData.forEach(user => {
      user.data.forEach(d => allDates.add(d.date));
    });
    
    // Sort dates
    const sortedDates = Array.from(allDates).sort();
    
    // Create chart data structure
    sortedDates.forEach(date => {
      const dataPoint: any = { date };
      userData.forEach((user, index) => {
        const userDayData = user.data.find(d => d.date === date);
        dataPoint[user.userName] = userDayData ? userDayData.totalTokens : 0;
      });
      chartData.push(dataPoint);
    });
    
    return (
      <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-100">
        <h2 className="text-xl font-semibold text-gray-800 mb-4">{title}</h2>
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={chartData} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
            <XAxis 
              dataKey="date" 
              stroke="#6b7280"
              tick={{ fontSize: 12 }}
            />
            <YAxis 
              stroke="#6b7280"
              tick={{ fontSize: 12 }}
            />
            <Tooltip content={<CustomTooltip />} />
            <Legend />
            {userData.map((user, index) => (
              <Line 
                key={user.userName}
                type="monotone" 
                dataKey={user.userName} 
                stroke={CHART_COLORS[index % CHART_COLORS.length]} 
                name={user.userName}
                strokeWidth={2}
                dot={{ r: 3 }}
                activeDot={{ r: 6 }}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    );
  };

  const renderStackedBarChart = (title: string, data: any[]) => (
    <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-100">
      <h2 className="text-xl font-semibold text-gray-800 mb-4">{title}</h2>
      <ResponsiveContainer width="100%" height={300}>
        <LineChart data={data} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
          <XAxis 
            dataKey="date" 
            stroke="#6b7280"
            tick={{ fontSize: 12 }}
          />
          <YAxis 
            stroke="#6b7280"
            tick={{ fontSize: 12 }}
          />
          <Tooltip content={<CustomTooltip />} />
          <Legend />
          <Line 
            type="monotone" 
            dataKey="promptTokens" 
            stroke="#6366f1" 
            name={t('dashboard.promptTokens')} 
            strokeWidth={2}
            dot={{ r: 3 }}
            activeDot={{ r: 6 }}
          />
          <Line 
            type="monotone" 
            dataKey="completionTokens" 
            stroke="#10b981" 
            name={t('dashboard.completionTokens')} 
            strokeWidth={2}
            dot={{ r: 3 }}
            activeDot={{ r: 6 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );

  const renderStatsTable = (title: string, data: Record<string, { totalTokens: number; promptTokens: number; completionTokens: number; requestCount: number }>, showUserEmail: boolean = false) => (
    <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-100">
      <h2 className="text-xl font-semibold text-gray-800 mb-4">{title}</h2>
      <div className="overflow-x-auto">
        <table className="min-w-full">
          <thead>
            <tr className="border-b border-gray-200">
              <th className="px-4 py-3 text-left text-sm font-medium text-gray-500 uppercase tracking-wider">{showUserEmail ? t('users.email') : t('dashboard.name')}</th>
              <th className="px-4 py-3 text-left text-sm font-medium text-gray-500 uppercase tracking-wider">{t('dashboard.promptTokens')}</th>
              <th className="px-4 py-3 text-left text-sm font-medium text-gray-500 uppercase tracking-wider">{t('dashboard.completionTokens')}</th>
              <th className="px-4 py-3 text-left text-sm font-medium text-gray-500 uppercase tracking-wider">{t('dashboard.totalTokens')}</th>
              <th className="px-4 py-3 text-left text-sm font-medium text-gray-500 uppercase tracking-wider">{t('dashboard.requestCount')}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {Object.entries(data).map(([name, values]) => (
              <tr key={name} className="hover:bg-gray-50">
                <td className="px-4 py-3 text-sm font-medium text-gray-900">{name}</td>
                <td className="px-4 py-3 text-sm text-gray-700">{values.promptTokens.toLocaleString()}</td>
                <td className="px-4 py-3 text-sm text-gray-700">{values.completionTokens.toLocaleString()}</td>
                <td className="px-4 py-3 text-sm font-semibold text-gray-900">{values.totalTokens.toLocaleString()}</td>
                <td className="px-4 py-3 text-sm text-gray-700">{values.requestCount.toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );

  // User stats cards - only show if userStats exists (admin user)
  const renderUserStats = () => {
    if (!stats.userStats) return null;
    
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
        <StatCard title={t('users.title')} value={stats.userStats.total} icon={<span className="text-indigo-600">👥</span>} color="bg-indigo-50" />
        <StatCard title={t('users.active')} value={stats.userStats.active} icon={<span className="text-green-600">✅</span>} color="bg-green-50" />
        <StatCard title={t('users.disabled')} value={stats.userStats.disabled} icon={<span className="text-red-600">🚫</span>} color="bg-red-50" />
        <StatCard title={t('users.validUntil')} value={stats.userStats.expired} icon={<span className="text-amber-600">⏰</span>} color="bg-amber-50" />
      </div>
    );
  };

  return (
    <main className="container mx-auto p-6">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900">{t('dashboard.title')}</h1>
        <p className="text-gray-600 mt-2">AI Gateway usage statistics and analytics</p>
      </div>

      {/* User stats for admin users */}
      {renderUserStats()}

      {/* Key metrics cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
        <StatCard 
          title={t('dashboard.totalRequests')} 
          value={totalRequests.toLocaleString()} 
          icon={<span className="text-blue-600">🚀</span>} 
          color="bg-blue-50" 
        />
        <StatCard 
          title={t('dashboard.totalTokens')} 
          value={totalTokens.toLocaleString()} 
          icon={<span className="text-purple-600">🪙</span>} 
          color="bg-purple-50" 
        />
        <StatCard 
          title={t('dashboard.providers')} 
          value={totalProviders} 
          icon={<span className="text-amber-600">📦</span>} 
          color="bg-amber-50" 
        />
        <StatCard 
          title={t('dashboard.models')} 
          value={totalModels} 
          icon={<span className="text-emerald-600">🧠</span>} 
          color="bg-emerald-50" 
        />
      </div>

      {/* Charts section */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
        {renderChart(t('dashboard.dailyUsage'), stats.dailyUsage, 'date', 'totalTokens', t('dashboard.totalTokens'), '#6366f1')}
        {renderChart(t('dashboard.weeklyUsage'), stats.weeklyUsage, 'date', 'totalTokens', t('dashboard.totalTokens'), '#8b5cf6')}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
        {renderStackedBarChart(t('dashboard.tokenUsageOverTime'), stats.tokenUsageOverTime)}
        {renderChart(t('dashboard.monthlyRequests'), stats.monthlyUsage, 'date', 'requestCount', t('dashboard.requestCount'), '#ec4899')}
      </div>

      {/* User-specific token usage chart - only show if userStats exists (admin user) */}
      {stats.userStats && stats.userTokenUsageOverTime.length > 0 && (
        <div className="mb-8">
          {renderMultiUserChart(t('dashboard.userTokenUsage'), stats.userTokenUsageOverTime)}
        </div>
      )}

      {/* Stats tables */}
      <div className="space-y-8">
        {renderStatsTable(t('dashboard.byProvider'), stats.byProvider)}
        {renderStatsTable(t('dashboard.byChannel'), stats.byChannel)}
        {renderStatsTable(t('dashboard.byModel'), stats.byModel)}
        {renderStatsTable(t('dashboard.byApiKey'), stats.byApiKey)}
        {stats.byUser && renderStatsTable(t('dashboard.byUser'), stats.byUser, true)}
      </div>
    </main>
  );
}
