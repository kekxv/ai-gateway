'use client';

import { useState, FormEvent } from 'react';
import { useRouter } from 'next/navigation';
import { useTranslation } from 'react-i18next';

export default function LoginPage() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [totpToken, setTotpToken] = useState('');
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();
  const { t } = useTranslation('common');

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);

    try {
      const response = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password, totpToken }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.error || t('login.failed'));
      }

      // Store the token (e.g., in localStorage or a secure cookie)
      localStorage.setItem('token', data.token);
      window.dispatchEvent(new Event('loginStatusChange')); // Dispatch custom event

      // Redirect to a protected page
      router.push('/dashboard');
    } catch (err) {
      setError(err instanceof Error ? err.message : t('common.unknownError'));
    }
  };

  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-4 bg-gray-50">
      <div className="w-full max-w-md bg-white p-8 rounded-2xl shadow-lg">
        <h1 className="text-3xl font-bold mb-8 text-center text-gray-800">{t('login.title')}</h1>
        <form onSubmit={handleSubmit} className="space-y-6">
          <div>
            <label htmlFor="email" className="block text-lg font-medium text-gray-700 mb-2">
              {t('login.username')}
            </label>
            <input
              type="text"
              id="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="p-4 w-full border rounded-lg focus:ring-2 focus:ring-blue-500 transition"
              required
            />
          </div>
          <div>
            <label htmlFor="password" className="block text-lg font-medium text-gray-700 mb-2">
              {t('login.password')}
            </label>
            <input
              type="password"
              id="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="p-4 w-full border rounded-lg focus:ring-2 focus:ring-blue-500 transition"
              required
            />
          </div>
          <div>
            <label htmlFor="totpToken" className="block text-lg font-medium text-gray-700 mb-2">
              {t('login.totpToken', 'Two-Factor Authentication Code')}
            </label>
            <input
              type="text"
              id="totpToken"
              value={totpToken}
              onChange={(e) => setTotpToken(e.target.value)}
              placeholder={t('login.totpPlaceholder', 'Enter code if enabled')}
              className="p-4 w-full border rounded-lg focus:ring-2 focus:ring-blue-500 transition"
            />
          </div>
          <button
            type="submit"
            className="w-full py-4 px-4 rounded-lg shadow-md text-lg font-semibold text-white bg-blue-600 hover:bg-blue-700 transition"
          >
            {t('login.signIn')}
          </button>
        </form>
        {error && <p className="mt-6 text-center text-red-600">{t('common.error')}: {error}</p>}
        
      </div>
    </main>
  );
}
