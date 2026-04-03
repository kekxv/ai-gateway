import { api } from './index'
import type { Channel, CreateChannelRequest, UpdateChannelRequest } from '@/types/channel'

interface ChannelListResponse {
  channels: Channel[]
  total: number
}

interface ProviderListResponse {
  providers: { id: number; name: string }[]
  total: number
}

interface ModelListResponse {
  models: { id: number; name: string }[]
  total: number
}

export const channelApi = {
  // List all channels
  list: (params?: { page?: number; page_size?: number }) =>
    api.get<ChannelListResponse>('/channels', { params }),

  // Get channel by ID
  get: (id: number) =>
    api.get<Channel>(`/channels/${id}`),

  // Create channel
  create: (data: CreateChannelRequest) =>
    api.post<Channel>('/channels', data),

  // Update channel
  update: (id: number, data: UpdateChannelRequest) =>
    api.put<Channel>(`/channels/${id}`, data),

  // Delete channel
  delete: (id: number) =>
    api.delete(`/channels/${id}`),

  // Bind providers to channel
  bindProviders: (id: number, providerIds: number[]) =>
    api.post(`/channels/${id}/providers`, { provider_ids: providerIds }),

  // Bind models to channel
  bindModels: (id: number, modelIds: number[]) =>
    api.post(`/channels/${id}/models`, { model_ids: modelIds })
}

// Export response types for use in views
export type { ChannelListResponse, ProviderListResponse, ModelListResponse }