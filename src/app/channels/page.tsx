'use client';

import { useState, useEffect, FormEvent, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { useTranslation } from 'react-i18next';

// Define types for better safety
type Provider = {
  id: number;
  name: string;
  baseURL: string;
};

type ProviderModel = {
  providerId: number;
  modelId: number;
  provider: Provider;
};

type Model = {
  id: number;
  name: string;
  description: string | null;
  alias?: string | null; // Add alias field
  providerModels: ProviderModel[]; // Include providerModels
};

type ModelRoute = {
  id: number;
  modelId: number;
  channelId: number;
  model: Model;
};

type Channel = {
  id: number;
  name: string;
  providerId: number;
  provider: Provider; // Nested provider object
  modelRoutes: ModelRoute[]; // Include model routes
  // Removed apiKey
};

export default function ChannelsPage() {
  const [channels, setChannels] = useState<Channel[]>([]);
  const [providers, setProviders] = useState<Provider[]>([]);
  const [allModels, setAllModels] = useState<Model[]>([]); // All models fetched
  const [filteredModels, setFilteredModels] = useState<Model[]>([]); // Models filtered by selected provider
  const [newChannel, setNewChannel] = useState({ name: '', providerId: '' }); // Removed apiKey
  const [selectedModelIds, setSelectedModelIds] = useState<number[]>([]);
  const [editingChannel, setEditingChannel] = useState<Channel | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [testPrompt, setTestPrompt] = useState('');
  const [testResponse, setTestResponse] = useState<string | null>(null);
  const [testingChannelId, setTestingChannelId] = useState<number | null>(null);
  const [testingModelId, setTestingModelId] = useState<number | null>(null);
  const [isTesting, setIsTesting] = useState(false); // New state for testing status
  const router = useRouter();
  const { t } = useTranslation('common');

  // Fetch channels, providers, and all models
  const fetchData = useCallback(async (token: string) => {
    try {
      setLoading(true);
      const headers = {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
      };

      const [channelsResponse, providersResponse, modelsResponse] = await Promise.all([
        fetch('/api/channels', { headers }),
        fetch('/api/providers', { headers }),
        fetch('/api/models', { headers }),
      ]);

      if (!channelsResponse.ok || !providersResponse.ok || !modelsResponse.ok) {
        if (channelsResponse.status === 401 || providersResponse.status === 401 || modelsResponse.status === 401) {
          router.push('/login');
          return;
        }
        throw new Error('获取数据失败');
      }

      const channelsData = await channelsResponse.json();
      const providersData = await providersResponse.json();
      const modelsData = await modelsResponse.json();
      
      setChannels(channelsData);
      setProviders(providersData);
      setAllModels(modelsData);

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
    fetchData(token);
  }, [fetchData, router]);

  // Filter models based on selected provider
  useEffect(() => {
    const currentProviderId = editingChannel ? editingChannel.providerId : parseInt(newChannel.providerId, 10);
    if (currentProviderId) {
      const modelsForProvider = allModels.filter(model => 
        model.providerModels && model.providerModels.some(pm => pm.providerId === currentProviderId)
      );
      setFilteredModels(modelsForProvider);
    } else {
      setFilteredModels([]);
    }
  }, [newChannel.providerId, editingChannel, allModels]);

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const { name, value } = e.target;
    if (editingChannel) {
      setEditingChannel(prev => ({ ...prev!, [name]: value }));
    } else {
      setNewChannel(prev => ({ ...prev, [name]: value }));
    }
  };

  const handleModelSelectChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const options = Array.from(e.target.selectedOptions).map(option => parseInt(option.value, 10));
    setSelectedModelIds(options);
  };

  const handleEdit = (channel: Channel) => {
    setEditingChannel(channel);
    setNewChannel({ name: channel.name, providerId: String(channel.providerId) });
    setSelectedModelIds(channel.modelRoutes.map(mr => mr.modelId));
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
      const method = editingChannel ? 'PUT' : 'POST';
      const url = editingChannel ? `/api/channels/${editingChannel.id}` : '/api/channels';
      const body = editingChannel ? 
        { 
          name: editingChannel.name, 
          providerId: parseInt(String(editingChannel.providerId), 10), 
          modelIds: selectedModelIds 
        } : 
        { 
          name: newChannel.name, 
          providerId: parseInt(newChannel.providerId, 10), 
          modelIds: selectedModelIds 
        };

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
        throw new Error(errorData.error || (editingChannel ? '更新渠道失败' : '创建渠道失败'));
      }

      // Clear form and refetch data
      setNewChannel({ name: '', providerId: '' });
      setSelectedModelIds([]); // Clear selected models
      setEditingChannel(null); // Clear editing state
      fetchData(token);
    } catch (err) {
      setError(err instanceof Error ? err.message : '发生未知错误');
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm(t('channels.deleteConfirm'))) return;

    const token = localStorage.getItem('token');
    if (!token) {
      router.push('/login');
      return;
    }

    try {
      const response = await fetch(`/api/channels/${id}`, {
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
        throw new Error(errorData.error || '删除渠道失败');
      }

      fetchData(token);
    } catch (err) {
      setError(err instanceof Error ? err.message : '发生未知错误');
    }
  };

  const handleTestChannelModel = async (channelId: number, modelId: number) => {
    if (!testPrompt) {
      setError(t('channels.enterTestPrompt'));
      return;
    }

    setIsTesting(true); // Set testing state to true
    setTestResponse(null);
    setError(null);

    const token = localStorage.getItem('token');
    if (!token) {
      router.push('/login');
      return;
    }

    try {
      const response = await fetch('/api/test-model', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({ channelId, modelId, prompt: testPrompt }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        if (response.status === 401) {
          router.push('/login');
          return;
        }
        throw new Error(errorData.error || '模型测试失败');
      }

      const data = await response.json();
      setTestResponse(JSON.stringify(data, null, 2)); // Pretty print JSON response
    } catch (err) {
      setError(err instanceof Error ? err.message : '发生未知错误');
    } finally {
      setIsTesting(false); // Set testing state to false
      // Keep the channel and model selection for convenience
    }
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
        <h1 className="text-3xl font-bold text-gray-900">{t('channels.title')}</h1>
        <p className="text-gray-600 mt-2">Manage AI channels and test model connections</p>
      </div>

      {/* Form to add/edit a channel */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-100 mb-8 overflow-hidden">
        <div className="px-6 py-5 border-b border-gray-200">
          <h2 className="text-xl font-semibold text-gray-900">
            {editingChannel ? t('channels.editChannel') : t('channels.addNewChannel')}
          </h2>
        </div>
        <div className="p-6">
          <form onSubmit={handleSubmit} className="space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div>
                <label htmlFor="channelName" className="block text-sm font-medium text-gray-700 mb-1">
                  {t('channels.channelName')}
                </label>
                <input
                  id="channelName"
                  type="text"
                  name="name"
                  value={editingChannel ? editingChannel.name : newChannel.name}
                  onChange={handleInputChange}
                  placeholder={t('channels.descriptiveName')}
                  className="block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm border p-2"
                  required
                />
                <p className="text-xs text-gray-500 mt-1">{t('channels.descriptiveName')}</p>
              </div>
              <div>
                <label htmlFor="providerId" className="block text-sm font-medium text-gray-700 mb-1">
                  {t('channels.provider')}
                </label>
                <div className="relative">
                  <select
                    id="providerId"
                    name="providerId"
                    value={editingChannel ? editingChannel.providerId : newChannel.providerId}
                    onChange={handleInputChange}
                    className="block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm border p-2"
                    required
                  >
                    <option value="" disabled>{t('channels.selectProvider')}</option>
                    {providers.map(provider => (
                      <option key={provider.id} value={provider.id}>
                        {provider.name}
                      </option>
                    ))}
                  </select>
                </div>
                <p className="text-xs text-gray-500 mt-1">{t('channels.selectProviderDescription')}</p>
              </div>
            </div>

            <div>
              <label htmlFor="models" className="block text-sm font-medium text-gray-700 mb-1">
                {t('channels.allowedModels')}
              </label>
              <div className="relative">
                <select
                  id="models"
                  multiple
                  value={selectedModelIds.map(String)}
                  onChange={handleModelSelectChange}
                  className="block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm border p-2 h-40"
                >
                  {filteredModels.map(model => (
                    <option key={model.id} value={model.id}>
                      {model.name}
                    </option>
                  ))}
                </select>
              </div>
              <p className="text-xs text-gray-500 mt-1">{t('channels.selectMultipleModels')}</p>
            </div>

            <div className="flex justify-end space-x-3">
              {editingChannel && (
                <button 
                  type="button" 
                  onClick={() => setEditingChannel(null)}
                  className="inline-flex items-center px-4 py-2 border border-gray-300 text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500"
                >
                  {t('channels.cancel')}
                </button>
              )}
              <button 
                type="submit" 
                className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500"
              >
                {editingChannel ? t('channels.updateChannel') : t('channels.addChannel')}
              </button>
            </div>
            {error && <p className="text-red-600 mt-4">{t('common.error')}: {error}</p>}
          </form>
        </div>
      </div>

      {/* List of existing channels */}
      <div className="mb-8">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-xl font-semibold text-gray-900">{t('channels.existingChannels')}</h2>
        </div>
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
          <div className="divide-y divide-gray-100">
            {channels.map(channel => (
              <div key={channel.id} className="p-5 hover:bg-gray-50 transition-colors duration-150">
                <div className="flex justify-between items-start">
                  <div className="flex-1 min-w-0">
                    <h3 className="text-lg font-medium text-gray-900 truncate">{channel.name}</h3>
                    <div className="mt-2 flex flex-wrap items-center gap-2 text-sm text-gray-500">
                      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-indigo-100 text-indigo-800">
                        {channel.provider?.name}
                      </span>
                      <span className="font-mono text-xs bg-gray-100 px-2 py-1 rounded">
                        {channel.provider?.baseURL}
                      </span>
                    </div>
                    {channel.modelRoutes.length > 0 && (
                      <div className="mt-3">
                        <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">
                          {t('channels.allowedModels')}
                        </p>
                        <div className="flex flex-wrap gap-1">
                          {channel.modelRoutes.map(mr => (
                            <span
                              key={mr.model.id} 
                              className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-green-100 text-green-800"
                            >
                              {mr.model?.name}
                              {mr.model?.alias && (
                                <span className="ml-1 text-green-600">({mr.model.alias})</span>
                              )}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                  <div className="flex space-x-2 ml-4">
                    <button 
                      onClick={() => handleEdit(channel)}
                      className="inline-flex items-center px-3 py-1 border border-transparent text-xs font-medium rounded-md text-indigo-700 bg-indigo-100 hover:bg-indigo-200 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500"
                    >
                      {t('channels.edit')}
                    </button>
                    <button 
                      onClick={() => handleDelete(channel.id)}
                      className="inline-flex items-center px-3 py-1 border border-transparent text-xs font-medium rounded-md text-red-700 bg-red-100 hover:bg-red-200 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500"
                    >
                      {t('channels.delete')}
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Model Testing Section */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
        <div className="px-6 py-5 border-b border-gray-200">
          <h2 className="text-xl font-semibold text-gray-900">{t('channels.modelTesting')}</h2>
        </div>
        <div className="p-6">
          <div className="space-y-5">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                {t('channels.selectChannel')}
              </label>
              <div className="relative">
                <select
                  value={testingChannelId || ''}
                  onChange={(e) => setTestingChannelId(parseInt(e.target.value, 10))}
                  className="block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm border p-2"
                >
                  <option value="">{t('channels.selectChannel')}</option>
                  {channels.map(channel => (
                    <option key={channel.id} value={channel.id}>
                      {channel.name} ({channel.provider?.name})
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {testingChannelId && (
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  {t('channels.selectModel')}
                </label>
                <div className="relative">
                  <select
                    value={testingModelId || ''}
                    onChange={(e) => setTestingModelId(parseInt(e.target.value, 10))}
                    className="block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm border p-2"
                  >
                    <option value="">{t('channels.selectModel')}</option>
                    {channels.find(c => c.id === testingChannelId)?.modelRoutes.map(mr => (
                      <option key={mr.id} value={mr.model.id}>
                        {mr.model?.name}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
            )}

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                {t('channels.testPromptPlaceholder')}
              </label>
              <textarea
                value={testPrompt}
                onChange={(e) => setTestPrompt(e.target.value)}
                placeholder={t('channels.testPromptPlaceholder')}
                rows={4}
                className="block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm border p-2"
              />
            </div>

            <div>
              <button
                onClick={() => testingChannelId && testingModelId && handleTestChannelModel(testingChannelId, testingModelId)}
                disabled={!testingChannelId || !testingModelId || !testPrompt || isTesting}
                className={`inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white focus:outline-none focus:ring-2 focus:ring-offset-2 ${
                  testingChannelId && testingModelId && testPrompt && !isTesting
                    ? 'bg-purple-600 hover:bg-purple-700 focus:ring-purple-500'
                    : 'bg-gray-400 cursor-not-allowed'
                }`}
              >
                {isTesting ? (
                  <>
                    <svg className="animate-spin -ml-1 mr-2 h-4 w-4 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                    {t('channels.testing')}
                  </>
                ) : (
                  <>
                    <svg className="-ml-1 mr-2 h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M14.828 14.828a4 4 0 01-5.656 0M9 10h.01M15 10h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    {testingChannelId && testingModelId ? t('channels.testChannelModel') : t('channels.selectChannelAndModel')}
                  </>
                )}
              </button>
            </div>

            {testResponse && (
              <div className="mt-4">
                <div className="flex items-center mb-2">
                  <svg className="mr-2 h-5 w-5 text-green-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  <h3 className="text-sm font-medium text-gray-900">{t('channels.testResponse')}:</h3>
                </div>
                <div className="bg-gray-50 rounded-lg p-4 font-mono text-sm overflow-auto max-h-60 border border-gray-200">
                  <pre className="whitespace-pre-wrap break-words">{testResponse}</pre>
                </div>
                <div className="mt-2 text-sm text-green-600">
                  {t('channels.testSuccess')}
                </div>
              </div>
            )}

            {error && (
              <div className="rounded-md bg-red-50 p-4">
                <div className="flex">
                  <div className="flex-shrink-0">
                    <svg className="h-5 w-5 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                  </div>
                  <div className="ml-3">
                    <h3 className="text-sm font-medium text-red-800">{t('common.error')}: {error}</h3>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </main>
  );
}
