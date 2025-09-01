'use client';

import { useState, useEffect, FormEvent, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { useTranslation } from 'react-i18next';

type Provider = {
  id: number;
  name: string;
  baseURL: string;
};

type ModelRoute = {
  id: number;
  modelId: number;
  providerId: number;
  weight: number;
};

type Model = {
  id: number;
  name: string;
  description: string | null;
  alias?: string | null;
  modelRoutes: ModelRoute[];
};

type Channel = {
  id: number;
  name: string;
  shared: boolean;
  providers: Provider[];
  models: Model[]; // Added models to channel type
};

export default function ChannelsPage() {
  const [channels, setChannels] = useState<Channel[]>([]);
  const [providers, setProviders] = useState<Provider[]>([]);
  const [allModels, setAllModels] = useState<Model[]>([]);
  const [filteredModels, setFilteredModels] = useState<Model[]>([]);
  const [newChannel, setNewChannel] = useState({ name: '', providerIds: [] as number[], shared: false });
  const [selectedModelIds, setSelectedModelIds] = useState<number[]>([]);
  const [editingChannel, setEditingChannel] = useState<Channel | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();
  const { t } = useTranslation('common');

  const fetchData = useCallback(async (token: string) => {
    try {
      setLoading(true);
      const headers = {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
      };

      // Fetch channels first, as they now contain the models we need.
      const channelsResponse = await fetch('/api/channels', { headers });
      if (!channelsResponse.ok) {
        if (channelsResponse.status === 401) router.push('/login');
        throw new Error('获取渠道失败');
      }
      const channelsData = await channelsResponse.json();
      setChannels(channelsData);

      // Then fetch providers and all models for the form selectors
      const [providersResponse, modelsResponse] = await Promise.all([
        fetch('/api/providers', { headers }),
        fetch('/api/models', { headers }),
      ]);

      if (!providersResponse.ok || !modelsResponse.ok) {
        if (providersResponse.status === 401 || modelsResponse.status === 401) router.push('/login');
        throw new Error('获取提供商或模型失败');
      }
      const providersData = await providersResponse.json();
      const modelsData = await modelsResponse.json();
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

  useEffect(() => {
    const selectedProviderIds = newChannel.providerIds || [];

    if (selectedProviderIds.length === 0) {
      setFilteredModels([]);
      return;
    }
    const modelsForSelectedProviders = allModels.filter(model => 
      model.modelRoutes.some(route => selectedProviderIds.includes(route.providerId))
    );
    setFilteredModels(modelsForSelectedProviders);
  }, [newChannel.providerIds, allModels]);

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    setNewChannel(prev => ({ ...prev, [name]: value }));
  };

  const handleEdit = (channel: Channel) => {
    setEditingChannel(channel);
    const providerIdsForChannel = channel.providers.map(p => p.id);
    setNewChannel({
      name: channel.name,
      providerIds: providerIdsForChannel,
      shared: channel.shared
    });

    // Use the models directly from the channel object
    setSelectedModelIds(channel.models.map(m => m.id));
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
      
      const body = {
        name: newChannel.name,
        providerIds: newChannel.providerIds,
        modelIds: selectedModelIds,
        shared: newChannel.shared
      };

      const response = await fetch(url, { method, headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` }, body: JSON.stringify(body) });

      if (!response.ok) {
        const errorData = await response.json();
        if (response.status === 401) router.push('/login');
        throw new Error(errorData.error || (editingChannel ? '更新渠道失败' : '创建渠道失败'));
      }

      setNewChannel({ name: '', providerIds: [], shared: false });
      setSelectedModelIds([]);
      setEditingChannel(null);
      fetchData(token);
    } catch (err) {
      setError(err instanceof Error ? err.message : '发生未知错误');
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm(t('channels.deleteConfirm'))) return;
    const token = localStorage.getItem('token');
    if (!token) { router.push('/login'); return; }

    try {
      const response = await fetch(`/api/channels/${id}`, { method: 'DELETE', headers: { 'Authorization': `Bearer ${token}` } });
      if (!response.ok) {
        const errorData = await response.json();
        if (response.status === 401) router.push('/login');
        throw new Error(errorData.error || '删除渠道失败');
      }
      fetchData(token);
    } catch (err) {
      setError(err instanceof Error ? err.message : '发生未知错误');
    }
  };

  if (loading) return <main className="container mx-auto p-6"><div className="flex justify-center items-center h-64"><div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-indigo-500"></div></div></main>;
  if (error) return <main className="container mx-auto p-6"><div className="bg-red-50 border border-red-200 rounded-lg p-6 text-center"><p className="text-red-700 font-medium">{t('common.error')}: {error}</p></div></main>;

  return (
    <main className="container mx-auto p-6">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900">{t('channels.title')}</h1>
        <p className="text-gray-600 mt-2">Manage AI channels and model bindings</p>
      </div>

      <div className="bg-white rounded-xl shadow-sm border border-gray-100 mb-8 overflow-hidden">
        <div className="px-6 py-5 border-b border-gray-200"><h2 className="text-xl font-semibold text-gray-900">{editingChannel ? t('channels.editChannel') : t('channels.addNewChannel')}</h2></div>
        <div className="p-6">
          <form onSubmit={handleSubmit} className="space-y-6">
            <div>
              <label htmlFor="channelName" className="block text-sm font-medium text-gray-700 mb-1">{t('channels.channelName')}</label>
              <input id="channelName" type="text" name="name" value={newChannel.name} onChange={handleInputChange} placeholder={t('channels.descriptiveName')} className="block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm border p-2" required />
            </div>
            
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">{t('channels.provider')}</label>
              <div className="border border-gray-200 rounded-xl p-3 bg-gray-50 max-h-48 overflow-y-auto">
                {providers.length > 0 ? (
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                    {providers.map(provider => (
                      <div key={provider.id} className={`flex items-center p-3 rounded-lg cursor-pointer transition-all duration-150 ${newChannel.providerIds.includes(provider.id) ? 'bg-indigo-100 border border-indigo-300' : 'bg-white border border-gray-200 hover:bg-gray-50'}`} onClick={() => { const newProviderIds = newChannel.providerIds.includes(provider.id) ? newChannel.providerIds.filter(id => id !== provider.id) : [...newChannel.providerIds, provider.id]; setNewChannel(prev => ({ ...prev, providerIds: newProviderIds })); }}>
                        <div className={`w-5 h-5 rounded-full border flex items-center justify-center mr-3 ${newChannel.providerIds.includes(provider.id) ? 'border-indigo-500 bg-indigo-500' : 'border-gray-300'}`}>
                          {newChannel.providerIds.includes(provider.id) && <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>}
                        </div>
                        <span className="text-sm font-medium text-gray-800">{provider.name}</span>
                      </div>
                    ))}
                  </div>
                ) : <p className="text-gray-500">{t('channels.noProvidersAvailable')}</p>}
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">{t('channels.allowedModels')}</label>
              <div className="border border-gray-200 rounded-xl p-3 bg-gray-50 max-h-48 overflow-y-auto">
                {filteredModels.length > 0 ? (
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                    {filteredModels.map(model => (
                      <div key={model.id} className={`flex items-center p-3 rounded-lg cursor-pointer transition-all duration-150 ${selectedModelIds.includes(model.id) ? 'bg-green-100 border border-green-300' : 'bg-white border border-gray-200 hover:bg-gray-50'}`} onClick={() => { const newSelectedModelIds = selectedModelIds.includes(model.id) ? selectedModelIds.filter(id => id !== model.id) : [...selectedModelIds, model.id]; setSelectedModelIds(newSelectedModelIds); }}>
                        <div className={`w-5 h-5 rounded-full border flex items-center justify-center mr-3 ${selectedModelIds.includes(model.id) ? 'border-green-500 bg-green-500' : 'border-gray-300'}`}>
                          {selectedModelIds.includes(model.id) && <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>}
                        </div>
                        <div>
                          <span className="text-sm font-medium text-gray-800">{model.name}</span>
                          {model.alias && <span className="block text-xs text-gray-500">{t('models.alias')}: {model.alias}</span>}
                        </div>
                      </div>
                    ))}
                  </div>
                ) : <p className="text-gray-500">{newChannel.providerIds.length > 0 ? t('channels.noModelsForSelectedProviders') : t('channels.selectProviderFirst')}</p>}
              </div>
            </div>
            <div>
              <label className="flex items-center cursor-pointer">
                <input
                  type="checkbox"
                  checked={newChannel.shared}
                  onChange={(e) => setNewChannel(prev => ({ ...prev, shared: e.target.checked }))}
                  className="rounded border-gray-300 text-indigo-600 shadow-sm focus:border-indigo-300 focus:ring focus:ring-indigo-200 focus:ring-opacity-50"
                />
                <span className="ml-2 text-sm text-gray-700">{t('channels.shareChannel')}</span>
              </label>
              <p className="mt-1 text-xs text-gray-500">{t('channels.shareChannelDescription')}</p>
            </div>
            <div className="flex justify-end space-x-3">
              {editingChannel && <button type="button" onClick={() => { setEditingChannel(null); setNewChannel({ name: '', providerIds: [], shared: false }); setSelectedModelIds([]); }} className="inline-flex items-center px-4 py-2 border border-gray-300 text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50">{t('channels.cancel')}</button>}
              <button type="submit" className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-indigo-600 hover:bg-indigo-700">{editingChannel ? t('channels.updateChannel') : t('channels.addChannel')}</button>
            </div>
            {error && <p className="text-red-600 mt-4">{t('common.error')}: {error}</p>}
          </form>
        </div>
      </div>

      <div className="mb-8">
        <h2 className="text-xl font-semibold text-gray-900">{t('channels.existingChannels')}</h2>
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
          <div className="divide-y divide-gray-100">
            {channels.map(channel => (
              <div key={channel.id} className="p-5 hover:bg-gray-50 transition-colors duration-150">
                <div className="flex justify-between items-start">
                  <div className="flex-1 min-w-0">
                    <h3 className="text-lg font-medium text-gray-900 truncate">{channel.name}</h3>
                    <div className="mt-2 flex flex-wrap items-center gap-2 text-sm text-gray-500">
                      {channel.providers.map(provider => (
                        <span key={provider.id} className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-indigo-100 text-indigo-800">{provider.name}</span>
                      ))}
                      {channel.shared && (
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-yellow-100 text-yellow-800">{t('channels.shared')}</span>
                      )}
                    </div>
                    {channel.models && channel.models.length > 0 && (
                      <div className="mt-3">
                        <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">{t('channels.allowedModels')}</p>
                        <div className="flex flex-wrap gap-1">
                          {channel.models.map(model => (
                            <span key={model.id} className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-green-100 text-green-800">{model.name}</span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                  <div className="flex space-x-2 ml-4">
                    <button onClick={() => handleEdit(channel)} className="inline-flex items-center px-3 py-1 border border-transparent text-xs font-medium rounded-md text-indigo-700 bg-indigo-100 hover:bg-indigo-200">{t('channels.edit')}</button>
                    <button onClick={() => handleDelete(channel.id)} className="inline-flex items-center px-3 py-1 border border-transparent text-xs font-medium rounded-md text-red-700 bg-red-100 hover:bg-red-200">{t('channels.delete')}</button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </main>
  );
}
