'use client';

import { useState, useEffect, FormEvent, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import ModelSelectionModal from '@/components/ModelSelectionModal'; // Import the modal
import { useTranslation } from 'react-i18next';

type Provider = {
  id: number;
  name: string;
  baseURL: string;
  apiKey: string;
  type?: string;
  autoLoadModels?: boolean;
};

export default function ProvidersPage() {
  const router = useRouter();
  const { t } = useTranslation('common');

  const [providers, setProviders] = useState<Provider[]>([]);
  const [newProvider, setNewProvider] = useState({ name: '', baseURL: '', apiKey: '', type: 'openai', autoLoadModels: false });
  const [editingProvider, setEditingProvider] = useState<Provider | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false); // State for modal visibility
  const [selectedProviderId, setSelectedProviderId] = useState<number | null>(null); // State for the selected provider
  const [notification, setNotification, ] = useState<string | null>(null);

  const fetchProviders = useCallback(async (token: string) => {
    try {
      setLoading(true);
      const response = await fetch('/api/providers', {
        headers: { 'Authorization': `Bearer ${token}` },
      });
      if (!response.ok) {
        if (response.status === 401) router.push('/login');
        throw new Error('获取提供商失败');
      }
      const data = await response.json();
      setProviders(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : '发生未知错误');
    } finally {
      setLoading(false);
    }
  }, [router]);

  useEffect(() => {
    const token = localStorage.getItem('token');
    if (!token) {
      router.push('/login');
      return;
    }
    fetchProviders(token);
  }, [fetchProviders, router]);

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    // eslint-disable-next-line @typescript-eslint/ban-ts-comment
    // @ts-expect-error
    const { name, value, type, checked } = e.target;
    const inputValue = type === 'checkbox' ? checked : value;
    if (editingProvider) {
      setEditingProvider(prev => ({ ...prev!, [name]: inputValue }));
    } else {
      setNewProvider(prev => ({ ...prev, [name]: inputValue }));
    }
  };

  const handleEdit = (provider: Provider) => {
    setEditingProvider(provider);
    setNewProvider({ name: provider.name, baseURL: provider.baseURL, apiKey: provider.apiKey, type: provider.type || 'openai', autoLoadModels: provider.autoLoadModels || false });
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    const token = localStorage.getItem('token');
    if (!token) {
      router.push('/login');
      return;
    }

    try {
      const method = editingProvider ? 'PUT' : 'POST';
      const url = editingProvider ? `/api/providers/${editingProvider.id}` : '/api/providers';
      const body = editingProvider ? 
        { name: editingProvider.name, baseURL: editingProvider.baseURL, apiKey: editingProvider.apiKey, type: editingProvider.type, autoLoadModels: editingProvider.autoLoadModels } :
        newProvider;

      const response = await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify(body),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || (editingProvider ? t('providers.updateFailed') : t('providers.createFailed')));
      }

      setNewProvider({ name: '', baseURL: '', apiKey: '', type: 'openai', autoLoadModels: false });
      setEditingProvider(null);
      fetchProviders(token);
    } catch (err) {
      setError(err instanceof Error ? err.message : '发生未知错误');
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm(t('providers.deleteConfirm'))) return;
    const token = localStorage.getItem('token');
    if (!token) {
      router.push('/login');
      return;
    }

    try {
      const response = await fetch(`/api/providers/${id}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` },
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || t('providers.deleteFailed'));
      }
      fetchProviders(token);
    } catch (err) {
      setError(err instanceof Error ? err.message : '发生未知错误');
    }
  };

  const handleLoadModelsClick = (providerId: number) => {
    setSelectedProviderId(providerId);
    setIsModalOpen(true);
  };

  const handleModalClose = () => {
    setIsModalOpen(false);
    setSelectedProviderId(null);
  };

  const handleModelsAdded = () => {
    setNotification(t('providers.modelsAdded'));
    setTimeout(() => setNotification(null), 3000); // Hide notification after 3 seconds
    const token = localStorage.getItem('token');
    if (token) fetchProviders(token); // Refresh provider data if needed
  };

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
        <h1 className="text-3xl font-bold text-gray-900">{t('providers.title')}</h1>
        <p className="text-gray-600 mt-2">Manage AI providers and their API configurations</p>
      </div>

      {notification && (
        <div className="mb-6 rounded-md bg-green-50 p-4">
          <div className="flex">
            <div className="flex-shrink-0">
              <svg className="h-5 w-5 text-green-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
            <div className="ml-3">
              <p className="text-sm font-medium text-green-800">{notification}</p>
            </div>
          </div>
        </div>
      )}

      <div className="bg-white rounded-xl shadow-sm border border-gray-100 mb-8 overflow-hidden">
        <div className="px-6 py-5 border-b border-gray-200">
          <h2 className="text-xl font-semibold text-gray-900">
            {editingProvider ? t('providers.editProvider') : t('providers.addNewProvider')}
          </h2>
        </div>
        <div className="p-6">
          <form onSubmit={handleSubmit} className="space-y-6">
            <div>
              <label htmlFor="providerName" className="block text-sm font-medium text-gray-700 mb-1">
                {t('providers.name')}
              </label>
              <input 
                id="providerName" 
                type="text" 
                name="name" 
                value={editingProvider ? editingProvider.name : newProvider.name} 
                onChange={handleInputChange} 
                placeholder={t('providers.namePlaceholder')} 
                className="block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm border p-2" 
                required 
              />
              <p className="text-xs text-gray-500 mt-1">{t('providers.nameDescription')}</p>
            </div>
            <div>
              <label htmlFor="baseURL" className="block text-sm font-medium text-gray-700 mb-1">
                {t('providers.baseURL')}
              </label>
              <input 
                id="baseURL" 
                type="text" 
                name="baseURL" 
                value={editingProvider ? editingProvider.baseURL : newProvider.baseURL} 
                onChange={handleInputChange} 
                placeholder={t('providers.baseURLPlaceholder')} 
                className="block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm border p-2" 
                required 
              />
              <p className="text-xs text-gray-500 mt-1">{t('providers.baseURLDescription')}</p>
            </div>
            <div>
              <label htmlFor="apiKey" className="block text-sm font-medium text-gray-700 mb-1">
                {t('providers.apiKey')}
              </label>
              <input 
                id="apiKey" 
                type="password" 
                name="apiKey" 
                value={editingProvider ? editingProvider.apiKey : newProvider.apiKey} 
                onChange={handleInputChange} 
                placeholder={t('providers.apiKeyPlaceholder')} 
                className="block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm border p-2" 
              />
              <p className="text-xs text-gray-500 mt-1">{t('providers.apiKeyDescription')}</p>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                {t('providers.type')}
              </label>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                {[
                  { value: 'openai', label: 'OpenAI', icon: '🤖' },
                  { value: 'gemini', label: 'Gemini', icon: '✨' },
                  { value: 'custom', label: t('providers.custom'), icon: '🔧' }
                ].map((type) => (
                  <div 
                    key={type.value}
                    onClick={() => handleInputChange({ 
                      target: { 
                        name: 'type', 
                        value: type.value 
                      } 
                    } as React.ChangeEvent<HTMLInputElement>)}
                    className={`border rounded-xl p-4 cursor-pointer transition-all duration-200 ease-in-out transform hover:scale-[1.02] ${
                      (editingProvider ? editingProvider.type || 'openai' : newProvider.type) === type.value
                        ? 'border-indigo-500 bg-indigo-50 ring-2 ring-indigo-200 shadow-sm'
                        : 'border-gray-200 hover:border-indigo-300 hover:bg-gray-50 shadow-sm'
                    }`}
                  >
                    <div className="flex items-center">
                      <span className="text-lg mr-3">{type.icon}</span>
                      <div>
                        <div className={`w-5 h-5 rounded-full border mr-3 inline-flex items-center justify-center ${
                          (editingProvider ? editingProvider.type || 'openai' : newProvider.type) === type.value
                            ? 'border-indigo-500 bg-indigo-500'
                            : 'border-gray-300'
                        }`}>
                          {(editingProvider ? editingProvider.type || 'openai' : newProvider.type) === type.value && (
                            <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" />
                            </svg>
                          )}
                        </div>
                        <span className="text-sm font-medium text-gray-800">{type.label}</span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
              <p className="text-xs text-gray-500 mt-2">{t('providers.typeDescription')}</p>
            </div>
            <div className="flex items-center">
              <input
                id="autoLoadModels"
                type="checkbox"
                name="autoLoadModels"
                checked={editingProvider ? editingProvider.autoLoadModels : newProvider.autoLoadModels}
                onChange={handleInputChange}
                className="h-4 w-4 text-indigo-600 focus:ring-indigo-500 border-gray-300 rounded"
              />
              <label htmlFor="autoLoadModels" className="ml-2 block text-sm text-gray-900">
                {t('providers.autoLoadModels')}
              </label>
              <p className="text-xs text-gray-500 ml-2">{t('providers.autoLoadModelsDescription')}</p>
            </div>
            <div className="flex justify-end space-x-3">
              {editingProvider && (
                <button 
                  type="button" 
                  onClick={() => setEditingProvider(null)}
                  className="inline-flex items-center px-4 py-2 border border-gray-300 text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500"
                >
                  {t('providers.cancel')}
                </button>
              )}
              <button 
                type="submit" 
                className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500"
              >
                {editingProvider ? t('providers.updateProvider') : t('providers.addProvider')}
              </button>
            </div>
            {error && <p className="text-red-600 mt-4">{t('common.error')}: {error}</p>}
          </form>
        </div>
      </div>

      <div className="mb-8">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-xl font-semibold text-gray-900">{t('providers.existingProviders')}</h2>
        </div>
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
          <div className="divide-y divide-gray-100">
            {providers.map(provider => (
              <div key={provider.id} className="p-5 hover:bg-gray-50 transition-colors duration-150">
                <div className="flex justify-between items-start">
                  <div className="flex-1 min-w-0">
                    <h3 className="text-lg font-medium text-gray-900 truncate">{provider.name}</h3>
                    <div className="mt-2 flex flex-wrap items-center gap-2">
                      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-indigo-100 text-indigo-800">
                        {provider.type || 'custom'}
                      </span>
                      <span className="font-mono text-xs bg-gray-100 px-2 py-1 rounded">
                        {provider.baseURL}
                      </span>
                      {!!provider.autoLoadModels && (
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-purple-100 text-purple-800">
                          {t('providers.autoLoadModelsEnabled')}
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="flex space-x-2 ml-4">
                    <button 
                      onClick={() => handleEdit(provider)}
                      className="inline-flex items-center px-3 py-1 border border-transparent text-xs font-medium rounded-md text-indigo-700 bg-indigo-100 hover:bg-indigo-200 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500"
                    >
                      {t('providers.edit')}
                    </button>
                    <button 
                      onClick={() => handleDelete(provider.id)}
                      className="inline-flex items-center px-3 py-1 border border-transparent text-xs font-medium rounded-md text-red-700 bg-red-100 hover:bg-red-200 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500"
                    >
                      {t('providers.delete')}
                    </button>
                    <button 
                      onClick={() => handleLoadModelsClick(provider.id)}
                      className="inline-flex items-center px-3 py-1 border border-transparent text-xs font-medium rounded-md text-green-700 bg-green-100 hover:bg-green-200 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-green-500"
                    >
                      {t('providers.loadModels')}
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {isModalOpen && selectedProviderId && (
        <ModelSelectionModal 
          providerId={selectedProviderId} 
          onClose={handleModalClose} 
          onModelsAdded={handleModelsAdded} 
        />
      )}
    </main>
  );
}
