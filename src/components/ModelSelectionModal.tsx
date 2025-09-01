'use client';

import { useState, useEffect, useCallback } from 'react';

type Model = {
  id: string;
  name: string;
  description?: string;
};

type ModelSelectionModalProps = {
  providerId: number;
  onClose: () => void;
  onModelsAdded: () => void;
};

export default function ModelSelectionModal({ providerId, onClose, onModelsAdded }: ModelSelectionModalProps) {
  const [models, setModels] = useState<Model[]>([]);
  const [selectedModels, setSelectedModels] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');

  const fetchModels = useCallback(async () => {
    setLoading(true);
    setError(null);
    const token = localStorage.getItem('token');
    if (!token) {
      setError('认证失败，请重新登录。');
      setLoading(false);
      return;
    }

    try {
      const response = await fetch(`/api/providers/${providerId}/load-models`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });

      if (!response.ok) {
        const errData = await response.json();
        throw new Error(errData.error || '获取模型列表失败');
      }

      const data: Model[] = await response.json();
      setModels(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : '发生未知错误');
    } finally {
      setLoading(false);
    }
  }, [providerId]);

  useEffect(() => {
    fetchModels();
  }, [fetchModels]);

  const handleSelectModel = (modelName: string) => {
    setSelectedModels(prev => {
      const newSelection = new Set(prev);
      if (newSelection.has(modelName)) {
        newSelection.delete(modelName);
      } else {
        newSelection.add(modelName);
      }
      return newSelection;
    });
  };

  const handleSelectAll = () => {
    const modelsToSelect = models.filter(model =>
      model.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      (model.description && model.description.toLowerCase().includes(searchTerm.toLowerCase()))
    );
    if (selectedModels.size === modelsToSelect.length) {
      setSelectedModels(new Set());
    } else {
      setSelectedModels(new Set(modelsToSelect.map(m => m.name)));
    }
  };

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    const token = localStorage.getItem('token');
    if (!token) {
      setError('认证失败，请重新登录。');
      setSaving(false);
      return;
    }

    try {
      const modelsToSave = models.filter(m => selectedModels.has(m.name));
      const response = await fetch('/api/models', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({ models: modelsToSave, providerId }),
      });

      if (!response.ok) {
        const errData = await response.json();
        throw new Error(errData.error || '保存模型失败');
      }

      onModelsAdded();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : '发生未知错误');
    } finally {
      setSaving(false);
    }
  };

  const filteredModels = models.filter(model =>
    model.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
    (model.description && model.description.toLowerCase().includes(searchTerm.toLowerCase()))
  );

  return (
    <div className="fixed inset-0 bg-gray-900 bg-opacity-30 backdrop-blur-md flex justify-center items-center z-50">
      <div className="bg-white rounded-2xl shadow-2xl p-8 max-w-4xl w-full max-h-[90vh] flex flex-col">
        <div className="flex justify-between items-center mb-6">
          <h2 className="text-2xl font-bold text-gray-800">选择要添加的模型</h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 transition-colors"
            aria-label="Close"
          >
            <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        
        {loading && <p className="text-gray-600">正在加载模型列表...</p>}
        {error && (
          <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded relative mb-4" role="alert">
            <strong className="font-bold">错误!</strong>
            <span className="block sm:inline"> {error}</span>
          </div>
        )}

        {!loading && !error && (
          <>
            <input
              type="text"
              placeholder="搜索模型..."
              className="w-full p-2 border border-gray-300 rounded-md mb-4"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
            />
            <div className="border-b pb-4 mb-4 flex justify-between items-center">
              <div className="flex items-center">
                <input
                  type="checkbox"
                  id="select-all"
                  className="h-5 w-5 rounded text-blue-600 focus:ring-blue-500 border-gray-300 shadow-sm"
                  checked={filteredModels.length > 0 && selectedModels.size === filteredModels.length}
                  onChange={handleSelectAll}
                />
                <label htmlFor="select-all" className="ml-3 text-lg font-medium text-gray-700">全选</label>
              </div>
              <span className="text-gray-500">已选择 {selectedModels.size} / {filteredModels.length}</span>
            </div>

            <div className="overflow-y-auto flex-grow grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 p-2">
              {filteredModels.map(model => (
                <div 
                  key={model.id} 
                  className={`flex flex-col items-start p-4 border rounded-lg shadow-sm hover:shadow-md transition-all duration-200 cursor-pointer relative ${selectedModels.has(model.name) ? 'border-blue-500 bg-blue-50' : 'border-gray-200 bg-white'}`}
                >
                  <input
                    type="checkbox"
                    id={`model-${model.id}`}
                    className="absolute top-3 right-3 h-5 w-5 rounded text-blue-600 focus:ring-blue-500 border-gray-300 shadow-sm"
                    checked={selectedModels.has(model.name)}
                    onChange={() => handleSelectModel(model.name)} 
                  />
                  <label htmlFor={`model-${model.id}`} className="flex-grow w-full pr-8 cursor-pointer">
                    <p className="font-semibold text-gray-800 text-lg mb-1">{model.name}</p>
                    {model.description && <p className="text-sm text-gray-500 line-clamp-2">{model.description}</p>}
                  </label>
                </div>
              ))}
            </div>

            <div className="mt-8 flex justify-end space-x-4">
              <button 
                onClick={onClose} 
                className="px-6 py-2 border border-gray-300 text-gray-700 font-semibold rounded-lg hover:bg-gray-100 transition shadow-sm"
              >
                取消
              </button>
              <button 
                onClick={handleSave} 
                className="px-6 py-2 bg-blue-600 text-white font-semibold rounded-lg hover:bg-blue-700 transition shadow-md disabled:bg-blue-300"
                disabled={saving || selectedModels.size === 0}
              >
                {saving ? '保存中...' : `添加 ${selectedModels.size} 个模型`}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
