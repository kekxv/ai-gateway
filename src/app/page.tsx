'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { useTranslation } from 'react-i18next';

export default function Home() {
  const router = useRouter();
  const { t } = useTranslation('common');

  useEffect(() => {
    const token = localStorage.getItem('token');
    if (token) {
      router.push('/dashboard');
    }
  }, [router]);

  return (
    <main className="flex min-h-screen flex-col items-center justify-center bg-gradient-to-br from-blue-500 to-purple-600 text-white">
      {/* Hero Section */}
      <section className="w-full text-center py-20 px-4">
        <h1 className="text-5xl md:text-6xl font-extrabold mb-6 leading-tight">
          {t('home.title')}
        </h1>
        <p className="text-xl md:text-2xl mb-10 max-w-3xl mx-auto opacity-90">
          {t('home.description')}
        </p>
        <div className="flex justify-center space-x-4">
          <Link href="/login" className="px-8 py-4 bg-white text-blue-600 font-bold rounded-full shadow-lg hover:bg-gray-100 transition transform hover:scale-105">
            {t('home.login')}
          </Link>
          <Link href="/register" className="px-8 py-4 border-2 border-white text-white font-bold rounded-full shadow-lg hover:bg-white hover:text-blue-600 transition transform hover:scale-105">
            {t('home.register')}
          </Link>
        </div>
      </section>

      {/* Features Section (Optional - can be added later) */}
      {/*
      <section className="w-full bg-white text-gray-800 py-16 px-4">
        <h2 className="text-4xl font-bold text-center mb-12">核心功能</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-10 max-w-6xl mx-auto">
          <div className="text-center p-6 rounded-lg shadow-md">
            <h3 className="text-2xl font-semibold mb-4">统一接口</h3>
            <p className="text-gray-600">通过一个统一的 API 接口访问多个 AI 服务提供商。</p>
          </div>
          <div className="text-center p-6 rounded-lg shadow-md">
            <h3 className="text-2xl font-semibold mb-4">智能路由</h3>
            <p className="text-gray-600">根据模型、负载等自动选择最佳渠道。</p>
          </div>
          <div className="text-center p-6 rounded-lg shadow-md">
            <h3 className="text-2xl font-semibold mb-4">用量统计</h3>
            <p className="text-gray-600">实时监控和分析您的 AI 服务使用情况。</p>
          }
        </div>
      </section>
      */}
    </main>
  );
}
