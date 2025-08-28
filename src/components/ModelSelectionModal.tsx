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
    if (selectedModels.size === models.length) {
      setSelectedModels(new Set());
    } else {
      setSelectedModels(new Set(models.map(m => m.name)));
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

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex justify-center items-center z-50">
      <div className="bg-white rounded-2xl shadow-2xl p-8 max-w-2xl w-full max-h-[90vh] flex flex-col">
        <h2 className="text-2xl font-bold mb-6 text-gray-800">选择要添加的模型</h2>
        
        {loading && <p className="text-gray-600">正在加载模型列表...</p>}
        {error && <p className="text-red-600">错误: {error}</p>}

        {!loading && !error && (
          <>
            <div className="border-b pb-4 mb-4 flex justify-between items-center">
              <div className="flex items-center">
                <input
                  type="checkbox"
                  id="select-all"
                  className="h-5 w-5 rounded text-blue-600 focus:ring-blue-500 border-gray-300 shadow-sm"
                  checked={models.length > 0 && selectedModels.size === models.length}
                  onChange={handleSelectAll}
                />
                <label htmlFor="select-all" className="ml-3 text-lg font-medium text-gray-700">全选</label>
              </div>
              <span className="text-gray-500">已选择 {selectedModels.size} / {models.length}</span>
            </div>

            <div className="overflow-y-auto flex-grow">
              {models.map(model => (
                <div key={model.id} className="flex items-center p-3 hover:bg-gray-50 rounded-lg">
                  <input
                    type="checkbox"
                    id={`model-${model.id}`}
                    className="h-5 w-5 rounded text-blue-600 focus:ring-blue-500 border-gray-300 shadow-sm"
                    checked={selectedModels.has(model.name)}
                    onChange={() => handleSelectModel(model.name)}
                  />
                  <label htmlFor={`model-${model.id}`} className="ml-4 flex-grow">
                    <p className="font-semibold text-gray-800">{model.name}</p>
                    {model.description && <p className="text-sm text-gray-500">{model.description}</p>}
                  </label>
                </div>
              ))}
            </div>

            <div className="mt-8 flex justify-end space-x-4">
              <button 
                onClick={onClose} 
                className="px-6 py-2 border border-gray-300 text-gray-700 font-semibold rounded-lg hover:bg-gray-100 transition shadow-sm"
                disabled={saving}
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
