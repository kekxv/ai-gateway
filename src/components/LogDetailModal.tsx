'use client';

import React from 'react';
import SyntaxHighlighter from 'react-syntax-highlighter';
import { atomOneLight } from 'react-syntax-highlighter/dist/esm/styles/hljs';
import { useTranslation } from 'react-i18next';

interface LogDetailModalProps {
  log: {
    id: number;
    createdAt: string;
    latency: number;
    promptTokens: number;
    completionTokens: number;
    totalTokens: number;
    cost: number;
    apiKey?: {
      name: string;
      user?: {
        email: string;
        role: string;
      };
    };
    modelName: string;
    providerName: string;
    logDetail?: {
      requestBody?: any;
      responseBody?: any;
    };
    ownerChannel?: {
      id: number;
      name: string;
      user?: {
        email: string;
      };
    };
  };
  onClose: () => void;
}

const JsonDisplay: React.FC<{ data: any }> = ({ data }) => {
  if (data === null || typeof data === 'undefined') return null;

  let displayData = data;
  if (typeof data === 'string') {
    try {
      displayData = JSON.parse(data);
    } catch (e) {
      displayData = data;
    }
  }

  const formattedJson = JSON.stringify(displayData, null, 2);

  return (
    <SyntaxHighlighter 
      language="json" 
      style={atomOneLight}
      customStyle={{
        borderRadius: '0.5rem',
        padding: '1rem',
        fontSize: '0.875rem',
        lineHeight: '1.5',
        margin: 0
      }}
    >
      {formattedJson}
    </SyntaxHighlighter>
  );
};

const LogDetailModal: React.FC<LogDetailModalProps> = ({ log, onClose }) => {
  const { t } = useTranslation('common');

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex justify-center items-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-4xl max-h-[90vh] overflow-hidden flex flex-col">
        {/* Modal Header */}
        <div className="px-6 py-4 border-b border-gray-200 flex justify-between items-center">
          <h2 className="text-xl font-bold text-gray-900">
            {t('logs.title')} (ID: {log.id})
          </h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-500 focus:outline-none"
          >
            <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Modal Body */}
        <div className="overflow-y-auto flex-1 p-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
            <div className="bg-gray-50 p-4 rounded-lg">
              <h3 className="text-sm font-medium text-gray-500 uppercase tracking-wider mb-2">{t('logs.timestamp')}</h3>
              <p className="text-gray-900">{new Date(log.createdAt).toLocaleString()}</p>
            </div>
            
            <div className="bg-gray-50 p-4 rounded-lg">
              <h3 className="text-sm font-medium text-gray-500 uppercase tracking-wider mb-2">{t('logs.apiKey')}</h3>
              <p className="text-gray-900">{log.apiKey?.name}</p>
            </div>
            
            {log.apiKey?.user && (
              <>
                <div className="bg-gray-50 p-4 rounded-lg">
                  <h3 className="text-sm font-medium text-gray-500 uppercase tracking-wider mb-2">{t('logs.userAccount')}</h3>
                  <p className="text-gray-900">{log.apiKey?.user?.email}</p>
                </div>
                
                <div className="bg-gray-50 p-4 rounded-lg">
                  <h3 className="text-sm font-medium text-gray-500 uppercase tracking-wider mb-2">{t('users.role')}</h3>
                  <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-indigo-100 text-indigo-800">
                    {log.apiKey?.user?.role}
                  </span>
                </div>
              </>
            )}
            
            <div className="bg-gray-50 p-4 rounded-lg">
              <h3 className="text-sm font-medium text-gray-500 uppercase tracking-wider mb-2">{t('logs.model')}</h3>
              <p className="text-gray-900">{log.modelName}</p>
            </div>
            
            <div className="bg-gray-50 p-4 rounded-lg">
              <h3 className="text-sm font-medium text-gray-500 uppercase tracking-wider mb-2">{t('logs.provider')}</h3>
              <p className="text-gray-900">{log.providerName}</p>
            </div>
            
            <div className="bg-gray-50 p-4 rounded-lg">
              <h3 className="text-sm font-medium text-gray-500 uppercase tracking-wider mb-2">{t('logs.latency')}</h3>
              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                {log.latency} ms
              </span>
            </div>
            
            <div className="bg-gray-50 p-4 rounded-lg">
              <h3 className="text-sm font-medium text-gray-500 uppercase tracking-wider mb-2">{t('logs.cost')}</h3>
              <p className="text-gray-900 font-semibold">¥{(log.cost / 10000).toFixed(4)}</p>
            </div>
            
            {log.ownerChannel && (
              <div className="bg-gray-50 p-4 rounded-lg">
                <h3 className="text-sm font-medium text-gray-500 uppercase tracking-wider mb-2">{t('logs.channel')}</h3>
                <p className="text-gray-900">{log.ownerChannel.name}</p>
                {log.ownerChannel.user && (
                  <p className="text-gray-500 text-sm">Owner: {log.ownerChannel.user.email}</p>
                )}
              </div>
            )}
            
            <div className="bg-gray-50 p-4 rounded-lg">
              <h3 className="text-sm font-medium text-gray-500 uppercase tracking-wider mb-2">{t('logs.totalTokens')}</h3>
              <p className="text-gray-900 font-semibold">{log.totalTokens.toLocaleString()}</p>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
            <div className="bg-indigo-50 p-4 rounded-lg">
              <h3 className="text-sm font-medium text-indigo-700 mb-1">{t('logs.promptTokens')}</h3>
              <p className="text-2xl font-bold text-indigo-900">{log.promptTokens.toLocaleString()}</p>
            </div>
            
            <div className="bg-green-50 p-4 rounded-lg">
              <h3 className="text-sm font-medium text-green-700 mb-1">{t('logs.completionTokens')}</h3>
              <p className="text-2xl font-bold text-green-900">{log.completionTokens.toLocaleString()}</p>
            </div>
            
            <div className="bg-purple-50 p-4 rounded-lg">
              <h3 className="text-sm font-medium text-purple-700 mb-1">{t('logs.totalTokens')}</h3>
              <p className="text-2xl font-bold text-purple-900">{log.totalTokens.toLocaleString()}</p>
            </div>
          </div>

          {log.logDetail?.requestBody && (
            <div className="mb-8">
              <h3 className="text-lg font-semibold text-gray-900 mb-3 flex items-center">
                <svg className="w-5 h-5 mr-2 text-indigo-600" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4"></path>
                </svg>
                {t('logs.requestBody')}
              </h3>
              <div className="rounded-lg overflow-hidden border border-gray-200">
                <JsonDisplay data={log.logDetail.requestBody} />
              </div>
            </div>
          )}

          {log.logDetail?.responseBody && (
            <div className="mb-6">
              <h3 className="text-lg font-semibold text-gray-900 mb-3 flex items-center">
                <svg className="w-5 h-5 mr-2 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4"></path>
                </svg>
                {t('logs.responseBody')}
              </h3>
              <div className="rounded-lg overflow-hidden border border-gray-200">
                <JsonDisplay data={log.logDetail.responseBody} />
              </div>
            </div>
          )}
        </div>

        {/* Modal Footer */}
        <div className="px-6 py-4 border-t border-gray-200 flex justify-end">
          <button
            onClick={onClose}
            className="inline-flex items-center px-4 py-2 border border-gray-300 text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500"
          >
            {t('common.close')}
          </button>
        </div>
      </div>
    </div>
  );
};

export default LogDetailModal;
