'use client';

import { useState, useEffect, FormEvent, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { useTranslation } from 'react-i18next';

// Define the type for a Gateway API Key
type GatewayApiKey = {
  id: number;
  name: string;
  key: string;
  enabled: boolean; // Add enabled field for editing
  createdAt: string;
};

export default function ApiKeysPage() {
  const [apiKeys, setApiKeys] = useState<GatewayApiKey[]>([]);
  const [newKeyName, setNewKeyName] = useState('');
  const [newlyCreatedKey, setNewlyCreatedKey] = useState<string | null>(null);
  const [editingKey, setEditingKey] = useState<GatewayApiKey | null>(null); // State for editing
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();
  const { t } = useTranslation('common');

  const fetchApiKeys = useCallback(async (token: string) => {
    try {
      setLoading(true);
      const response = await fetch('/api/keys', {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });
      if (!response.ok) {
        if (response.status === 401) {
          router.push('/login');
          return;
        }
        throw new Error(t('keys.fetchFailed'));
      }
      const data = await response.json();
      setApiKeys(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('common.unknownError'));
    } finally {
      setLoading(false);
    }
  }, [router, t]); // router is a dependency of fetchApiKeys

  useEffect(() => {
    const token = localStorage.getItem('token');
    if (!token) {
      router.push('/login');
      return;
    }
    fetchApiKeys(token);
  }, [fetchApiKeys, router]);

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value, type, checked } = e.target;
    if (editingKey) {
      setEditingKey(prev => ({ ...prev!, [name]: type === 'checkbox' ? checked : value }));
    } else {
      setNewKeyName(value);
    }
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setNewlyCreatedKey(null);

    const token = localStorage.getItem('token');
    if (!token) {
      router.push('/login');
      return;
    }

    try {
      const method = editingKey ? 'PUT' : 'POST';
      const url = editingKey ? `/api/keys/${editingKey.id}` : '/api/keys';
      const body = editingKey ? { name: editingKey.name, enabled: editingKey.enabled } : { name: newKeyName };

      const response = await fetch(url, {
        method,
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify(body),
      });

      if (!response.ok) {
        const errorData = await response.json();
        if (response.status === 401) {
          router.push('/login');
          return;
        }
        throw new Error(errorData.error || (editingKey ? t('keys.updateFailed') : t('keys.createFailed')));
      }

      if (!editingKey) {
        const createdKey = await response.json();
        setNewlyCreatedKey(createdKey.key);
      }
      setNewKeyName('');
      setEditingKey(null); // Clear editing state
      fetchApiKeys(token); // Refetch to show the new/updated key in the list
    } catch (err) {
      setError(err instanceof Error ? err.message : t('common.unknownError'));
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm(t('keys.deleteConfirm'))) return;

    const token = localStorage.getItem('token');
    if (!token) {
      router.push('/login');
      return;
    }

    try {
      const response = await fetch(`/api/keys/${id}`, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });

      if (!response.ok) {
        const errorData = await response.json();
        if (response.status === 401) {
          router.push('/login');
          return;
        }
        throw new Error(errorData.error || t('keys.deleteFailed'));
      }

      fetchApiKeys(token);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('common.unknownError'));
    }
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text).then(() => {
      alert(t('keys.copied'));
    });
  };

  const apiBaseUrl = typeof window !== 'undefined' ? window.location.origin : '';

  const curlExample = (key: string) => `curl -X POST ${apiBaseUrl}/api/v1/chat/completions \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer ${key}" \\
  -d '{ 
    "model": "gpt-3.5-turbo", 
    "messages": [{"role": "user", "content": "Hello, world!"}]
  }'`;

  const curlStreamExample = (key: string) => `curl -X POST ${apiBaseUrl}/api/v1/chat/completions \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer ${key}" \\
  -d '{ 
    "model": "gpt-3.5-turbo", 
    "messages": [{"role": "user", "content": "Tell me a story."}], 
    "stream": true
  }'`;

  if (loading) {
    return (
      <main className="container mx-auto p-6">
        <div className="flex justify-center items-center h-64">
          <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-indigo-500"></div>
        </div>
      </main>
    );
  }

  if (error) {
    return (
      <main className="container mx-auto p-6">
        <div className="bg-red-50 border border-red-200 rounded-lg p-6 text-center">
          <p className="text-red-700 font-medium">{t('common.error')}: {error}</p>
        </div>
      </main>
    );
  }

  return (
    <main className="container mx-auto p-6">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900">{t('keys.title')}</h1>
        <p className="text-gray-600 mt-2">{t('keys.apiExamples')}</p>
      </div>

      {/* Form to generate/edit a key */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-100 mb-8 overflow-hidden">
        <div className="px-6 py-5 border-b border-gray-200">
          <h2 className="text-xl font-semibold text-gray-900">
            {editingKey ? t('keys.editKey') : t('keys.generateKey')}
          </h2>
        </div>
        <div className="p-6">
          <form onSubmit={handleSubmit} className="space-y-6">
            <div>
              <label htmlFor="keyName" className="block text-sm font-medium text-gray-700 mb-1">
                {t('keys.keyName')}
              </label>
              <input
                id="keyName"
                type="text"
                name="name"
                value={editingKey ? editingKey.name : newKeyName}
                onChange={handleInputChange}
                placeholder={t('keys.namePlaceholder')}
                className="block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm border p-2"
                required
              />
              <p className="text-xs text-gray-500 mt-1">{t('keys.nameDescription')}</p>
            </div>

            {editingKey && (
              <div className="flex items-center">
                <input
                  id="enabled"
                  type="checkbox"
                  name="enabled"
                  checked={editingKey.enabled}
                  onChange={handleInputChange}
                  className="h-4 w-4 text-indigo-600 focus:ring-indigo-500 border-gray-300 rounded"
                />
                <label htmlFor="enabled" className="ml-2 block text-sm text-gray-900">
                  {t('keys.enabled')}
                </label>
                <p className="text-xs text-gray-500 mt-1 ml-2">{t('keys.enabledDescription')}</p>
              </div>
            )}

            <div className="flex justify-end space-x-3">
              {editingKey && (
                <button 
                  type="button" 
                  onClick={() => setEditingKey(null)}
                  className="inline-flex items-center px-4 py-2 border border-gray-300 text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500"
                >
                  {t('keys.cancel')}
                </button>
              )}
              <button 
                type="submit" 
                className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500"
              >
                {editingKey ? t('keys.updateKey') : t('keys.addKey')}
              </button>
            </div>
            {error && <p className="text-red-600 mt-4">{t('common.error')}: {error}</p>}
          </form>
        </div>
      </div>

      {/* Display newly created key */}
      {newlyCreatedKey && (
        <div className="mb-8 bg-green-50 border border-green-200 rounded-lg p-6">
          <div className="flex items-center">
            <svg className="h-5 w-5 text-green-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <h3 className="ml-2 text-lg font-medium text-green-800">{t('keys.newKeyGenerated')}</h3>
          </div>
          <p className="mt-2 text-sm text-green-700">{t('keys.saveKey')}</p>
          <div className="mt-4 flex items-center justify-between p-3 bg-white rounded-lg font-mono text-sm break-all border border-green-200">
            <span className="text-green-800">{newlyCreatedKey}</span>
            <button 
              onClick={() => copyToClipboard(newlyCreatedKey)} 
              className="ml-4 inline-flex items-center px-3 py-1 border border-transparent text-xs font-medium rounded-md shadow-sm text-white bg-green-600 hover:bg-green-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-green-500"
            >
              {t('keys.copy')}
            </button>
          </div>
        </div>
      )}

      {/* List of existing keys */}
      <div className="mb-8">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-xl font-semibold text-gray-900">{t('keys.existingKeys')}</h2>
        </div>
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
          <div className="divide-y divide-gray-100">
            {apiKeys.map(apiKey => (
              <div key={apiKey.id} className="p-5 hover:bg-gray-50 transition-colors duration-150">
                <div className="flex justify-between items-start">
                  <div className="flex-1 min-w-0">
                    <h3 className="text-lg font-medium text-gray-900 truncate">{apiKey.name}</h3>
                    <div className="mt-2 flex flex-wrap items-center gap-2">
                      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-800 font-mono">
                        {`${apiKey.key.substring(0, 8)}...${apiKey.key.substring(apiKey.key.length - 4)}`}
                      </span>
                      <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                        apiKey.enabled 
                          ? 'bg-green-100 text-green-800' 
                          : 'bg-red-100 text-red-800'
                      }`}>
                        {apiKey.enabled ? t('keys.enabled') : t('keys.disabled')}
                      </span>
                    </div>
                    <p className="mt-2 text-sm text-gray-500">
                      {t('keys.createdAt')}: {new Date(apiKey.createdAt).toLocaleString()}
                    </p>
                  </div>
                  <div className="flex space-x-2 ml-4">
                    <button 
                      onClick={() => setEditingKey(apiKey)}
                      className="inline-flex items-center px-3 py-1 border border-transparent text-xs font-medium rounded-md text-indigo-700 bg-indigo-100 hover:bg-indigo-200 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500"
                    >
                      {t('keys.edit')}
                    </button>
                    <button 
                      onClick={() => handleDelete(apiKey.id)}
                      className="inline-flex items-center px-3 py-1 border border-transparent text-xs font-medium rounded-md text-red-700 bg-red-100 hover:bg-red-200 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500"
                    >
                      {t('keys.delete')}
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* API Interface List and Examples */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
        <div className="px-6 py-5 border-b border-gray-200">
          <h2 className="text-xl font-semibold text-gray-900">{t('keys.apiExamples')}</h2>
        </div>
        <div className="p-6">
          <div className="space-y-8">
            <div>
              <h3 className="text-lg font-medium text-gray-900 mb-2">{t('keys.chatCompletion')}</h3>
              <p className="text-sm text-gray-500 mb-3">{t('keys.chatCompletionDescription')}</p>
              <div className="bg-gray-50 rounded-lg p-4 font-mono text-sm overflow-auto border border-gray-200">
                <pre className="whitespace-pre-wrap break-words">{curlExample('YOUR_API_KEY')}</pre>
              </div>
            </div>
            <div>
              <h3 className="text-lg font-medium text-gray-900 mb-2">{t('keys.streamChatCompletion')}</h3>
              <p className="text-sm text-gray-500 mb-3">{t('keys.streamChatCompletionDescription')}</p>
              <div className="bg-gray-50 rounded-lg p-4 font-mono text-sm overflow-auto border border-gray-200">
                <pre className="whitespace-pre-wrap break-words">{curlStreamExample('YOUR_API_KEY')}</pre>
              </div>
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}
