// Stats types
export interface UsageStats {
  name: string
  requests: number
  tokens: number
  promptTokens: number
  completionTokens: number
  cost: number
}

export interface DailyUsage {
  date: string
  requests: number
  tokens: number
  promptTokens: number
  completionTokens: number
  cost: number
}

export interface UserTokenUsage {
  userName: string
  data: DailyUsage[]
}

export interface UserStats {
  total: number
  active: number
  disabled: number
  expired: number
}

export interface Stats {
  byProvider: UsageStats[]
  byModel: UsageStats[]
  byApiKey: UsageStats[]
  byUser: UsageStats[]
  dailyUsage: DailyUsage[]
  weeklyUsage: DailyUsage[]
  monthlyUsage: DailyUsage[]
  tokenUsageOverTime: DailyUsage[]
  userTokenUsageOverTime: UserTokenUsage[]
  userStats: UserStats
  totalCost: number
  totalRequests: number
  totalTokens: number
  providerCount: number
  modelCount: number
}