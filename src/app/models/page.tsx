'use client';

import {useState, useEffect, FormEvent, useCallback} from 'react';
import {useRouter} from 'next/navigation';
import {useTranslation} from 'react-i18next';

type Provider = {
  id: number;
  name: string;
  baseURL: string;
};

type ModelRoute = {
  id?: number; // Optional for new routes
  providerId: number;
  provider?: Provider;
  weight: number;
  disabled?: boolean;
};

type Model = {
  id: number;
  name: string;
  description: string | null;
  alias: string | null;
  createdAt: string;
  inputTokenPrice: number;
  outputTokenPrice: number;
  modelRoutes: ModelRoute[];
};

export default function ModelsPage() {
  const [models, setModels] = useState<Model[]>([]);
  const [providers, setProviders] = useState<Provider[]>([]);
  const [newModel, setNewModel] = useState({
    name: '',
    description: '',
    alias: '',
    inputTokenPrice: 0,
    outputTokenPrice: 0
  });
  const [editingModel, setEditingModel] = useState<Model | null>(null);
  const [editingModelRoutes, setEditingModelRoutes] = useState<ModelRoute[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedProviderId, setSelectedProviderId] = useState<number | null>(null);
  const router = useRouter();
  const {t} = useTranslation('common');

  const fetchModelsAndProviders = useCallback(async (token: string) => {
    try {
      setLoading(true);
      const headers = {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
      };

      const [modelsResponse, providersResponse] = await Promise.all([
        fetch('/api/models', {headers}),
        fetch('/api/providers', {headers}),
      ]);

      if (!modelsResponse.ok || !providersResponse.ok) {
        if (modelsResponse.status === 401 || providersResponse.status === 401) {
          router.push('/login');
          return;
        }
        throw new Error(t('models.fetchFailed'));
      }

      const modelsData = await modelsResponse.json();
      const providersData = await providersResponse.json();
      setModels(modelsData);
      setProviders(providersData);

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
    const {name, value, type} = e.target;
    const newValue = type === 'number' ? parseFloat(value) : value; // Parse number inputs
    if (editingModel) {
      setEditingModel(prev => ({...prev!, [name]: newValue}));
    } else {
      setNewModel(prev => ({...prev, [name]: newValue}));
    }
  };

  const handleEdit = (model: Model) => {
    setEditingModel(model);
    setNewModel({
      name: model.name,
      description: model.description || '',
      alias: model.alias || '',
      inputTokenPrice: model.inputTokenPrice, // Keep in 厘
      outputTokenPrice: model.outputTokenPrice // Keep in 厘
    });
    setEditingModelRoutes(model.modelRoutes.map(route => ({
      ...route,
      disabled: route.disabled || false // Copy disabled status for each route
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
          alias: editingModel.alias,
          inputTokenPrice: editingModel.inputTokenPrice, // Keep in 厘
          outputTokenPrice: editingModel.outputTokenPrice, // Keep in 厘
          modelRoutes: editingModelRoutes.map(route => ({
            providerId: route.providerId,
            weight: route.weight,
            disabled: route.disabled
          })),
        } :
        {
          ...newModel,
          alias: newModel.alias,
          inputTokenPrice: newModel.inputTokenPrice, // Keep in 厘
          outputTokenPrice: newModel.outputTokenPrice, // Keep in 厘
          modelRoutes: editingModelRoutes.map(route => ({
            providerId: route.providerId,
            weight: route.weight,
            disabled: route.disabled
          })),
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

      setNewModel({name: '', description: '', alias: '', inputTokenPrice: 0, outputTokenPrice: 0});
      setEditingModelRoutes([]);
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

            {/* New: Pricing Fields */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div>
                <label htmlFor="inputTokenPrice" className="block text-sm font-medium text-gray-700 mb-1">
                  {t('models.inputTokenPrice')} ({t('models.pricePerThousandTokens')} - 厘)
                </label>
                <input
                  id="inputTokenPrice"
                  type="number"
                  name="inputTokenPrice"
                  value={editingModel ? editingModel.inputTokenPrice : newModel.inputTokenPrice}
                  onChange={handleInputChange}
                  placeholder="0.00"
                  step="0.01"
                  min="0"
                  className="block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm border p-2"
                  required
                />
              </div>
              <div>
                <label htmlFor="outputTokenPrice" className="block text-sm font-medium text-gray-700 mb-1">
                  {t('models.outputTokenPrice')} ({t('models.pricePerThousandTokens')} - 厘)
                </label>
                <input
                  id="outputTokenPrice"
                  type="number"
                  name="outputTokenPrice"
                  value={editingModel ? editingModel.outputTokenPrice : newModel.outputTokenPrice}
                  onChange={handleInputChange}
                  placeholder="0.00"
                  step="0.01"
                  min="0"
                  className="block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm border p-2"
                  required
                />
              </div>
            </div>

            {/* Model Route Management - Provider Selection with Weight */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                {t('models.modelRoutes')}
              </label>
              <p className="text-sm text-gray-500 mb-3">{t('models.providerSelectionDescription')}</p>

              {providers.length === 0 ? (
                <div className="text-center py-4 bg-gray-50 rounded-lg">
                  <p className="text-gray-500">{t('models.noProvidersAvailable')}</p>
                </div>
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                  {providers.map(provider => {
                    const existingRouteIndex = editingModelRoutes.findIndex(route => route.providerId === provider.id);
                    const isSelected = existingRouteIndex !== -1;
                    const weight = isSelected ? editingModelRoutes[existingRouteIndex].weight : 1;

                    return (
                      <div
                        key={provider.id}
                        className={`border rounded-lg p-4 cursor-pointer transition-all duration-200 ${
                          isSelected
                            ? 'border-indigo-500 bg-indigo-50 ring-2 ring-indigo-100'
                            : 'border-gray-200 hover:border-indigo-300 hover:bg-gray-50'
                        }`}
                        onClick={() => {
                          if (isSelected) {
                            const updatedRoutes = editingModelRoutes.filter(route => route.providerId !== provider.id);
                            setEditingModelRoutes(updatedRoutes);
                          } else {
                            setEditingModelRoutes([...editingModelRoutes, {providerId: provider.id, weight: 1}]);
                          }
                        }}
                      >
                        <div className="flex items-start">
                          <div
                            className={`flex-shrink-0 w-5 h-5 rounded-full border flex items-center justify-center mt-0.5 ${
                              isSelected
                                ? 'border-indigo-500 bg-indigo-500'
                                : 'border-gray-300'
                            }`}>
                            {isSelected && (
                              <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7"/>
                              </svg>
                            )}
                          </div>
                          <div className="ml-3 flex-1">
                            <h4 className="text-sm font-medium text-gray-900">{provider.name}</h4>
                          </div>
                        </div>

                        {isSelected && (
                          <div className="mt-3 flex items-center">
                            <label className="text-xs font-medium text-gray-700 mr-2">{t('models.weight')}:</label>
                            <input
                              type="number"
                              value={weight}
                              onClick={(e) => e.stopPropagation()}
                              onChange={(e) => {
                                e.stopPropagation();
                                const newWeight = parseInt(e.target.value, 10) || 1;
                                const updatedRoutes = [...editingModelRoutes];
                                const index = updatedRoutes.findIndex(route => route.providerId === provider.id);
                                if (index !== -1) {
                                  updatedRoutes[index] = {...updatedRoutes[index], weight: newWeight};
                                  setEditingModelRoutes(updatedRoutes);
                                }
                              }}
                              className="w-16 rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 text-sm border p-1"
                              min="1"
                            />
                            <div className="ml-4 flex items-center">
                              <input
                                id={`route-disabled-${provider.id}`}
                                type="checkbox"
                                name="disabled"
                                checked={editingModelRoutes[existingRouteIndex]?.disabled || false}
                                onChange={(e) => {
                                  e.stopPropagation();
                                  const newDisabledStatus = e.target.checked;
                                  const updatedRoutes = [...editingModelRoutes];
                                  const index = updatedRoutes.findIndex(route => route.providerId === provider.id);
                                  if (index !== -1) {
                                    updatedRoutes[index] = {...updatedRoutes[index], disabled: newDisabledStatus};
                                    setEditingModelRoutes(updatedRoutes);
                                  }
                                }}
                                className="h-4 w-4 text-indigo-600 focus:ring-indigo-500 border-gray-300 rounded"
                              />
                              <label htmlFor={`route-disabled-${provider.id}`}
                                     className="ml-2 block text-sm text-gray-900">
                                {t('models.disabled')}
                              </label>
                            </div>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
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
        <div className="mb-4">
          <input
            type="text"
            placeholder={t('models.searchModels')}
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm border p-2"
          />
        </div>
        <div className="mb-4">
          <label className="block text-sm font-medium text-gray-700 mb-1">
            {t('models.filterByProvider')}
          </label>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2">
            {/* "All Providers" card */}
            <div
              className={`border rounded-lg p-2 cursor-pointer transition-all duration-200 text-center
                ${selectedProviderId === null ? 'border-indigo-500 bg-indigo-50 ring-2 ring-indigo-100' : 'border-gray-200 hover:border-indigo-300 hover:bg-gray-50'}`}
              onClick={() => setSelectedProviderId(null)}
            >
              <h4 className="text-xs font-medium text-gray-900">{t('models.allProviders')}</h4>
            </div>

            {/* Provider cards */}
            {providers.map(provider => (
              <div
                key={provider.id}
                className={`border rounded-lg p-2 cursor-pointer transition-all duration-200 text-center
                  ${selectedProviderId === provider.id ? 'border-indigo-500 bg-indigo-50 ring-2 ring-indigo-100' : 'border-gray-200 hover:border-indigo-300 hover:bg-gray-50'}`}
                onClick={() => setSelectedProviderId(provider.id)}
              >
                <h4 className="text-xs font-medium text-gray-900">{provider.name}</h4>
              </div>
            ))}
          </div>
        </div>
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden p-3">
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {models.filter(model => {
              const matchesSearchTerm = (
                model.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
                (model.alias && model.alias.toLowerCase().includes(searchTerm.toLowerCase())) ||
                (model.description && model.description.toLowerCase().includes(searchTerm.toLowerCase()))
              );

              const matchesProvider = (
                selectedProviderId === null ||
                model.modelRoutes.some(route => route.providerId === selectedProviderId)
              );

              return matchesSearchTerm && matchesProvider;
            }).map(model => (
              <div key={model.id}
                   className="flex flex-col p-3 border border-gray-200 rounded-lg shadow-sm hover:shadow-md transition-all duration-200">
                <div className="flex-1 min-w-0 mb-2">
                  <h3 className="text-lg font-medium text-gray-900 truncate mb-1">
                    {model.name}
                    {model.alias && (
                      <span className="ml-2 px-1.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                        {t('models.alias')}: {model.alias}
                      </span>
                    )}
                  </h3>
                  {model.description && <p className="text-xs text-gray-500 line-clamp-2">{model.description}</p>}
                  <div className="mt-1 text-sm text-gray-600">
                    <p>Input Price: {model.inputTokenPrice}/1K</p>
                    <p>Output Price: {model.outputTokenPrice}/1K</p>
                  </div>
                </div>

                {model.modelRoutes.length > 0 && (
                  <div className="mb-2">
                    <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">
                      {t('models.routes')}
                    </p>
                    <div className="flex flex-wrap gap-1">
                      {model.modelRoutes.map(mr => {
                        const provider = providers.find(p => p.id === mr.providerId);
                        return (
                          <span
                            key={mr.providerId}
                            className={`inline-flex items-center px-1.5 py-0.5 rounded-full text-xs font-medium ${mr.disabled ? 'bg-red-100 text-red-800' : 'bg-indigo-100 text-indigo-800'}`}
                          >
                            {provider?.name || 'N/A'} (W: {mr.weight}){(!!mr.disabled) && ' (Disabled)'}
                          </span>
                        );
                      })}
                    </div>
                  </div>
                )}

                <p className="text-xs text-gray-500 mt-auto">
                  {t('models.createdAt')}: {new Date(model.createdAt).toLocaleString()}
                </p>

                <div className="flex space-x-2 mt-3 pt-3 border-t border-gray-100">
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
