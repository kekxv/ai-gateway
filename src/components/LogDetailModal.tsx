'use client';

import React from 'react';
import SyntaxHighlighter from 'react-syntax-highlighter';
import { atomOneLight } from 'react-syntax-highlighter/dist/esm/styles/hljs';
import { useTranslation } from 'react-i18next';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

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
  loading?: boolean;
}
const LoadingSkeleton: React.FC = () => (
  <div className="animate-pulse space-y-4">
    <div className="h-4 bg-gray-200 rounded w-3/4"></div>
    <div className="h-4 bg-gray-200 rounded"></div>
    <div className="h-4 bg-gray-200 rounded w-5/6"></div>
  </div>
);

// OpenAI聊天消息类型
type OpenAIChatMessage = {
  role: 'user' | 'assistant' | 'system';
  content: string;
};

// 解析包含messages字段的对象
const parseMessagesFromObject = (obj: any): OpenAIChatMessage[] => {
  if (!obj) return [];
  
  // 如果是一个字符串，则尝试解析为JSON
  if (typeof obj === 'string') {
    try {
      const parsed = JSON.parse(obj);
      if (parsed.messages && Array.isArray(parsed.messages)) {
        return parsed.messages.map((item: any) => ({
          role: item.role,
          content: typeof item.content === 'string' ? item.content : JSON.stringify(item.content, null, 2)
        }));
      }
      // 处理OpenAI响应体中的choices
      if (parsed.choices && Array.isArray(parsed.choices)) {
        return parsed.choices.map((choice: any) => ({
          role: choice.message?.role || 'assistant',
          content: choice.message?.content || JSON.stringify(choice, null, 2)
        }));
      }
    } catch (_e) {
      // 如果解析失败，按原样返回
      return [{
        role: 'user',
        content: obj
      }];
    }
  }
  
  // 如果已经是对象且有messages属性（数组形式）
  if (obj.messages && Array.isArray(obj.messages)) {
    return obj.messages.map((item: any) => ({
      role: item.role,
      content: typeof item.content === 'string' ? item.content : JSON.stringify(item.content, null, 2)
    }));
  }
  
  // 处理OpenAI响应体中的choices
  if (obj.choices && Array.isArray(obj.choices)) {
    return obj.choices.map((choice: any) => ({
      role: choice.message?.role || 'assistant',
      content: choice.message?.content || JSON.stringify(choice, null, 2)
    }));
  }
  
  // 如果是字符串形式的JSON对象
  if (typeof obj === 'string') {
    try {
      const parsed = JSON.parse(obj);
      if (parsed.messages && Array.isArray(parsed.messages)) {
        return parsed.messages.map((item: any) => ({
          role: item.role,
          content: typeof item.content === 'string' ? item.content : JSON.stringify(item.content, null, 2)
        }));
      }
      // 处理OpenAI响应体中的choices
      if (parsed.choices && Array.isArray(parsed.choices)) {
        return parsed.choices.map((choice: any) => ({
          role: choice.message?.role || 'assistant',
          content: choice.message?.content || JSON.stringify(choice, null, 2)
        }));
      }
    } catch (_e) {
      // 如果还是不行，返回简单消息
      return [{
        role: 'user',
        content: obj
      }];
    }
  }
  
  // 如果是数组形式的messages
  if (Array.isArray(obj)) {
    return obj.map((item: any) => ({
      role: item.role,
      content: typeof item.content === 'string' ? item.content : JSON.stringify(item.content, null, 2)
    }));
  }
  
  // 默认情况
  return [{
    role: 'user',
    content: JSON.stringify(obj, null, 2)
  }];
};

// 提取OpenAI聊天历史记录
const extractChatHistory = (data: any): OpenAIChatMessage[] => {
  // 处理各种可能的数据格式
  if (!data) return [];
  
  // 如果是字符串格式的JSON对象
  if (typeof data === 'string') {
    try {
      const parsed = JSON.parse(data);
      return parseMessagesFromObject(parsed);
    } catch (_e) {
      // 如果是纯文本，作为单条消息返回
      return [{
        role: 'user',
        content: data
      }];
    }
  }
  
  // 如果是对象或数组
  if (typeof data === 'object') {
    return parseMessagesFromObject(data);
  }
  
  // 默认情况
  return [{
    role: 'user',
    content: JSON.stringify(data, null, 2)
  }];
};

const renderContent = (content: string) => {
  // 尝试解析为JSON并进行格式化
  try {
    const parsed = JSON.parse(content);
    return (
      <pre className="whitespace-pre-wrap break-words">
        {JSON.stringify(parsed, null, 2)}
      </pre>
    );
  } catch (_e) {
    // 如果不是JSON，检查是否为Markdown格式
    // if (isMarkdown(content)) {
      return (
        <ReactMarkdown remarkPlugins={[remarkGfm]}>
          {content}
        </ReactMarkdown>
      );
    // }
  }
};

const LogDetailModal: React.FC<LogDetailModalProps> = ({ log, onClose, loading }) => {
  const { t } = useTranslation('common');

  // 将请求体和响应体转换为OpenAI聊天消息格式
  const getChatMessages = (): OpenAIChatMessage[] => {
    const messages: OpenAIChatMessage[] = [];
    
    if (log.logDetail?.requestBody) {
      const requestMessages = extractChatHistory(log.logDetail.requestBody);
      messages.push(...requestMessages);
    }
    
    if (log.logDetail?.responseBody) {
      const responseMessages = extractChatHistory(log.logDetail.responseBody);
      messages.push(...responseMessages);
    }
    
    return messages;
  };

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
          {/* 简化版信息区域 */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
            <div className="bg-gray-50 p-3 rounded-lg">
              <h3 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-1">{t('logs.timestamp')}</h3>
              <p className="text-sm text-gray-900">{log.createdAt}</p>
            </div>
            
            <div className="bg-gray-50 p-3 rounded-lg">
              <h3 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-1">{t('logs.apiKey')}</h3>
              <p className="text-sm text-gray-900">{log.apiKey?.name}</p>
            </div>
            
            <div className="bg-gray-50 p-3 rounded-lg">
              <h3 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-1">{t('logs.model')}</h3>
              <p className="text-sm text-gray-900">{log.modelName}</p>
            </div>
            
            <div className="bg-gray-50 p-3 rounded-lg">
              <h3 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-1">{t('logs.provider')}</h3>
              <p className="text-sm text-gray-900">{log.providerName}</p>
            </div>
            
            <div className="bg-gray-50 p-3 rounded-lg">
              <h3 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-1">{t('logs.latency')}</h3>
              <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                {log.latency} ms
              </span>
            </div>
            
            <div className="bg-gray-50 p-3 rounded-lg">
              <h3 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-1">{t('logs.cost')}</h3>
              <p className="text-sm font-medium text-gray-900">¥{(log.cost / 10000).toFixed(4)}</p>
            </div>
          </div>

          {/* 详细信息区域 */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
            <div className="bg-indigo-50 p-3 rounded-lg">
              <h3 className="text-xs font-medium text-indigo-700 mb-1">{t('logs.promptTokens')}</h3>
              <p className="text-lg font-bold text-indigo-900">{log.promptTokens.toLocaleString()}</p>
            </div>
            
            <div className="bg-green-50 p-3 rounded-lg">
              <h3 className="text-xs font-medium text-green-700 mb-1">{t('logs.completionTokens')}</h3>
              <p className="text-lg font-bold text-green-900">{log.completionTokens.toLocaleString()}</p>
            </div>
            
            <div className="bg-purple-50 p-3 rounded-lg">
              <h3 className="text-xs font-medium text-purple-700 mb-1">{t('logs.totalTokens')}</h3>
              <p className="text-lg font-bold text-purple-900">{log.totalTokens.toLocaleString()}</p>
            </div>
          </div>

          {/* 聊天窗口样式的内容展示 */}
          {loading ? (
            <div className="mb-6">
              <div className="flex items-start justify-end mb-4">
                <div className="flex-1 text-right">
                  <div className="bg-indigo-100 rounded-lg rounded-tr-none p-4 inline-block">
                    <LoadingSkeleton />
                  </div>
                </div>
                <div className="flex-shrink-0 w-8 h-8 rounded-full bg-indigo-500 flex items-center justify-center text-white font-bold ml-3">
                  U
                </div>
              </div>
              
              <div className="flex items-start mb-4">
                <div className="flex-shrink-0 w-8 h-8 rounded-full bg-green-500 flex items-center justify-center text-white font-bold mr-3">
                  A
                </div>
                <div className="flex-1">
                  <div className="bg-green-100 rounded-lg rounded-tl-none p-4">
                    <LoadingSkeleton />
                  </div>
                </div>
              </div>
            </div>
          ) : (
            <div className="mb-6">
              {getChatMessages().length > 0 ? (
                <div className="flex flex-col space-y-4">
                  {getChatMessages().map((message, index) => (
                    <div 
                      key={index} 
                      className={`flex items-start ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
                    >
                      {message.role === 'user' ? (
                        <>
                          <div className="flex-1 text-right">
                            <div className="bg-indigo-100 rounded-lg rounded-tr-none p-4 inline-block max-w-[80%]">
                              <div className="text-xs font-medium mb-1">
                                {message.role.charAt(0).toUpperCase() + message.role.slice(1)}
                              </div>
                              <div className="text-sm text-left">
                                {renderContent(message.content)}
                              </div>
                            </div>
                          </div>
                          <div className="flex-shrink-0 w-8 h-8 rounded-full bg-indigo-500 flex items-center justify-center text-white font-bold ml-3">
                            U
                          </div>
                        </>
                      ) : (
                        <>
                          <div className="flex-shrink-0 w-8 h-8 rounded-full bg-green-500 flex items-center justify-center text-white font-bold mr-3">
                            A
                          </div>
                          <div className="flex-1">
                            <div className="bg-green-100 rounded-lg rounded-tl-none p-4 max-w-[80%]">
                              <div className="text-xs font-medium mb-1">
                                {message.role.charAt(0).toUpperCase() + message.role.slice(1)}
                              </div>
                              <div className="text-sm">
                                {renderContent(message.content)}
                              </div>
                            </div>
                          </div>
                        </>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-center py-8 text-gray-500">
                  {t('logs.noDataAvailable')}
                </div>
              )}
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
