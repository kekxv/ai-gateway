import { api } from './index'
import type { Channel, CreateChannelRequest, UpdateChannelRequest } from '@/types/channel'

export const channelApi = {
  // List all channels (returns full list, no pagination)
  list: () =>
    api.get<Channel[]>('/channels'),

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