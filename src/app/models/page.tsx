'use client';

import { useState, useEffect, FormEvent, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { useTranslation } from 'react-i18next';

type Provider = {
  id: number;
  name: string;
  baseURL: string;
};

type Channel = {
  id: number;
  name: string;
  providerId: number;
  provider: Provider; // Include provider for display
  enabled: boolean;
};

type ModelRoute = {
  id?: number; // Optional for new routes
  channelId: number;
  channel?: Channel; // Include channel for display
  weight: number;
};

type Model = {
  id: number;
  name: string;
  description: string | null;
  alias: string | null; // New alias field
  createdAt: string;
  modelRoutes: ModelRoute[]; // NEW: Array of model routes
};

export default function ModelsPage() {
  const [models, setModels] = useState<Model[]>([]);
  const [providers, setProviders] = useState<Provider[]>([]); // New state for all available providers
  const [channels, setChannels] = useState<Channel[]>([]); // NEW state for all available channels
  const [newModel, setNewModel] = useState({ name: '', description: '', alias: '' });
  const [editingModel, setEditingModel] = useState<Model | null>(null);
  const [editingModelRoutes, setEditingModelRoutes] = useState<ModelRoute[]>([]); // NEW state for managing routes
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();
  const { t } = useTranslation('common');

  const fetchModelsAndProviders = useCallback(async (token: string) => {
    try {
      setLoading(true);
      const headers = {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
      };

      const [modelsResponse, providersResponse, channelsResponse] = await Promise.all([
        fetch('/api/models', { headers }),
        fetch('/api/providers', { headers }),
        fetch('/api/channels', { headers }), // NEW
      ]);

      if (!modelsResponse.ok || !providersResponse.ok || !channelsResponse.ok) {
        if (modelsResponse.status === 401 || providersResponse.status === 401 || channelsResponse.status === 401) {
          router.push('/login');
          return;
        }
        throw new Error(t('models.fetchFailed'));
      }

      const modelsData = await modelsResponse.json();
      const providersData = await providersResponse.json();
      const channelsData = await channelsResponse.json(); // NEW
      
      setModels(modelsData);
      setProviders(providersData);
      setChannels(channelsData);

    } catch (err) {
      setError(err instanceof Error ? err.message : t('common.unknownError'));
    } finally {
      setLoading(false);
    }
  }, [router, t]);

  useEffect(() => {
    const token = localStorage.getItem('token');
    if (!token) {
      router.push('/login');
      return;
    }
    fetchModelsAndProviders(token);
  }, [fetchModelsAndProviders, router]);

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    const { name, value } = e.target;
    if (editingModel) {
      setEditingModel(prev => ({ ...prev!, [name]: value }));
    } else {
      setNewModel(prev => ({ ...prev, [name]: value }));
    }
  };

  const handleEdit = (model: Model) => {
    setEditingModel(model);
    setNewModel({ name: model.name, description: model.description || '', alias: model.alias || '' });
    // Populate editingModelRoutes with existing routes, ensuring channel data is available
    setEditingModelRoutes(model.modelRoutes.map(route => ({
      ...route,
      channel: channels.find(c => c.id === route.channelId) // Ensure channel object is present for display
    })));
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
      const method = editingModel ? 'PUT' : 'POST';
      const url = editingModel ? `/api/models/${editingModel.id}` : '/api/models';
      const body = editingModel ? 
        {
          name: editingModel.name,
          description: editingModel.description,
          alias: editingModel.alias, // Include alias
          modelRoutes: editingModelRoutes.map(route => ({ channelId: route.channelId, weight: route.weight })) // Send only necessary data
        } : 
        {
          ...newModel,
          alias: newModel.alias, // Include alias
          modelRoutes: editingModelRoutes.map(route => ({ channelId: route.channelId, weight: route.weight }))
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
        throw new Error(errorData.error || (editingModel ? t('models.updateFailed') : t('models.createFailed')));
      }

      setNewModel({ name: '', description: '', alias: '' }); // Clear alias
      setEditingModelRoutes([]); // Clear routes
      setEditingModel(null);
      fetchModelsAndProviders(token);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('common.unknownError'));
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm(t('models.deleteConfirm'))) return;

    const token = localStorage.getItem('token');
    if (!token) {
      router.push('/login');
      return;
    }

    try {
      const response = await fetch(`/api/models/${id}`, {
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
        throw new Error(errorData.error || t('models.deleteFailed'));
      }

      fetchModelsAndProviders(token);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('common.unknownError'));
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
        <h1 className="text-3xl font-bold text-gray-900">{t('models.title')}</h1>
        <p className="text-gray-600 mt-2">Manage AI models and their routing configurations</p>
      </div>

      {/* Form to add/edit a model */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-100 mb-8 overflow-hidden">
        <div className="px-6 py-5 border-b border-gray-200">
          <h2 className="text-xl font-semibold text-gray-900">
            {editingModel ? t('models.editModel') : t('models.addNewModel')}
          </h2>
        </div>
        <div className="p-6">
          <form onSubmit={handleSubmit} className="space-y-6">
            <div>
              <label htmlFor="modelName" className="block text-sm font-medium text-gray-700 mb-1">
                {t('models.name')}
              </label>
              <input
                id="modelName"
                type="text"
                name="name"
                value={editingModel ? editingModel.name : newModel.name}
                onChange={handleInputChange}
                placeholder={t('models.namePlaceholder')}
                className="block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm border p-2"
                required
              />
            </div>
            <div>
              <label htmlFor="modelDescription" className="block text-sm font-medium text-gray-700 mb-1">
                {t('models.description')}
              </label>
              <textarea
                id="modelDescription"
                name="description"
                value={editingModel ? editingModel.description || '' : newModel.description}
                onChange={handleInputChange}
                placeholder={t('models.descriptionPlaceholder')}
                rows={3}
                className="block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm border p-2"
              />
            </div>
            <div>
              <label htmlFor="modelAlias" className="block text-sm font-medium text-gray-700 mb-1">
                {t('models.alias')}
              </label>
              <input
                id="modelAlias"
                type="text"
                name="alias"
                value={editingModel ? editingModel.alias || '' : newModel.alias}
                onChange={handleInputChange}
                placeholder={t('models.aliasPlaceholder')}
                className="block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm border p-2"
              />
              <p className="text-xs text-gray-500 mt-1">{t('models.aliasDescription')}</p>
            </div>

            {/* Model Route Management */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                {t('models.modelRoutes')}
              </label>
              <div className="space-y-3">
                {editingModelRoutes.map((route, index) => (
                  <div key={index} className="flex items-center space-x-3 p-3 bg-gray-50 rounded-lg">
                    <div className="flex-grow">
                      <select
                        value={route.channelId}
                        onChange={(e) => {
                          const newChannelId = parseInt(e.target.value, 10);
                          const updatedRoutes = [...editingModelRoutes];
                          updatedRoutes[index] = {
                            ...updatedRoutes[index],
                            channelId: newChannelId,
                            channel: channels.find(c => c.id === newChannelId) // Update channel object
                          };
                          setEditingModelRoutes(updatedRoutes);
                        }}
                        className="block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm border p-2"
                      >
                        <option value="">{t('models.selectChannel')}</option>
                        {channels.map(channel => (
                          <option key={channel.id} value={channel.id}>
                            {channel.name} ({channel.provider.name})
                          </option>
                        ))}
                      </select>
                    </div>
                    <div className="w-24">
                      <input
                        type="number"
                        value={route.weight}
                        onChange={(e) => {
                          const newWeight = parseInt(e.target.value, 10);
                          const updatedRoutes = [...editingModelRoutes];
                          updatedRoutes[index] = { ...updatedRoutes[index], weight: newWeight };
                          setEditingModelRoutes(updatedRoutes);
                        }}
                        placeholder={t('models.weightPlaceholder')}
                        className="block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm border p-2"
                        min="1"
                      />
                    </div>
                    <button
                      type="button"
                      onClick={() => {
                        const updatedRoutes = editingModelRoutes.filter((_, i) => i !== index);
                        setEditingModelRoutes(updatedRoutes);
                      }}
                      className="inline-flex items-center p-2 border border-transparent rounded-md text-red-700 bg-red-100 hover:bg-red-200 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500"
                    >
                      <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                      </svg>
                    </button>
                  </div>
                ))}
              </div>
              <button
                type="button"
                onClick={() => setEditingModelRoutes([...editingModelRoutes, { channelId: 0, weight: 1 }])}
                className="mt-3 inline-flex items-center px-3 py-2 border border-dashed border-gray-300 text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500"
              >
                <svg className="-ml-1 mr-1 h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
                </svg>
                {t('models.addRoute')}
              </button>
            </div>

            <div className="flex justify-end space-x-3">
              {editingModel && (
                <button 
                  type="button" 
                  onClick={() => setEditingModel(null)}
                  className="inline-flex items-center px-4 py-2 border border-gray-300 text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500"
                >
                  {t('models.cancelEdit')}
                </button>
              )}
              <button 
                type="submit" 
                className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500"
              >
                {editingModel ? t('models.updateModel') : t('models.addModel')}
              </button>
            </div>
            {error && <p className="text-red-600 mt-3">{t('common.error')}: {error}</p>}
          </form>
        </div>
      </div>

      {/* List of existing models */}
      <div className="mb-8">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-xl font-semibold text-gray-900">{t('models.existingModels')}</h2>
        </div>
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden p-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {models.map(model => (
              <div key={model.id} className="flex flex-col p-4 border border-gray-200 rounded-lg shadow-sm hover:shadow-md transition-all duration-200">
                <div className="flex-1 min-w-0 mb-4">
                  <h3 className="text-lg font-medium text-gray-900 truncate mb-1">
                    {model.name}
                    {model.alias && (
                      <span className="ml-2 px-2 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                        {t('models.alias')}: {model.alias}
                      </span>
                    )}
                  </h3>
                  {model.description && <p className="text-sm text-gray-500 line-clamp-2">{model.description}</p>}
                </div>
                
                {model.modelRoutes.length > 0 && (
                  <div className="mb-4">
                    <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">
                      {t('models.routes')}
                    </p>
                    <div className="flex flex-wrap gap-1">
                      {model.modelRoutes.map(mr => (
                        <span 
                          key={mr.channelId} 
                          className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-indigo-100 text-indigo-800"
                        >
                          {mr.channel?.name || 'N/A'} (W: {mr.weight})
                        </span>
                      ))}
                    </div>
                  </div>
                )}
                
                <p className="text-xs text-gray-500 mt-auto">
                  {t('models.createdAt')}: {new Date(model.createdAt).toLocaleString()}
                </p>

                <div className="flex space-x-2 mt-4 pt-4 border-t border-gray-100">
                  <button 
                    onClick={() => handleEdit(model)}
                    className="inline-flex items-center px-3 py-1 border border-transparent text-xs font-medium rounded-md text-indigo-700 bg-indigo-100 hover:bg-indigo-200 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500"
                  >
                    {t('models.edit')}
                  </button>
                  <button 
                    onClick={() => handleDelete(model.id)}
                    className="inline-flex items-center px-3 py-1 border border-transparent text-xs font-medium rounded-md text-red-700 bg-red-100 hover:bg-red-200 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500"
                  >
                    {t('models.delete')}
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </main>
  );
}
