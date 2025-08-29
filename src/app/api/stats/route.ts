import { NextResponse } from 'next/server';
import { authMiddleware, AuthenticatedRequest } from '@/lib/auth'; // Import authMiddleware
import { getInitializedDb } from '@/lib/db';

export const GET = authMiddleware(async (request: AuthenticatedRequest) => {
  try {
    const now = new Date();
    const twentyFourHoursAgo = new Date(now.getTime() - 24 * 60 * 60 * 1000);
    const sevenDaysAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
    const thirtyDaysAgo = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);

    const userId = request.user?.userId;
    const userRole = request.user?.role;

    let logWhereClause: any = {
      createdAt: {
        gte: thirtyDaysAgo, // Fetch logs from the last 30 days for more comprehensive stats
      },
    };

    if (userRole !== 'ADMIN') {
      // For non-admin users, filter logs by their API keys
      logWhereClause = {
        ...logWhereClause,
        apiKey: {
          userId: userId,
        },
      };
    }

    const db = await getInitializedDb();

    let logQuery = `
      SELECT
        l.id, l.latency, l.promptTokens, l.completionTokens, l.totalTokens, l.createdAt,
        ak.name AS apiKeyName, ak.userId AS apiKeyUserId,
        u.email AS userEmail, u.role AS userRole,
        mr.modelId, mr.channelId,
        m.name AS modelName,
        c.name AS channelName,
        p.name AS providerName
      FROM Log l
      JOIN GatewayApiKey ak ON l.apiKeyId = ak.id
      LEFT JOIN User u ON ak.userId = u.id
      JOIN ModelRoute mr ON l.modelRouteId = mr.id
      JOIN Model m ON mr.modelId = m.id
      JOIN Channel c ON mr.channelId = c.id
      JOIN Provider p ON c.providerId = p.id
      WHERE l.createdAt >= ?
    `;
    const logQueryParams: any[] = [thirtyDaysAgo.toISOString()];

    if (userRole !== 'ADMIN') {
      logQuery += ` AND ak.userId = ?`;
      logQueryParams.push(userId);
    }

    logQuery += ` ORDER BY l.createdAt ASC`;

    const logs = await db.all(logQuery, ...logQueryParams);

    // Fetch user statistics - only admins can see this
    let userStats = null;
    if (userRole === 'ADMIN') {
      const totalUsersResult = await db.get('SELECT COUNT(*) as count FROM User');
      const totalUsers = totalUsersResult.count;

      const activeUsersResult = await db.get(
        `SELECT COUNT(*) as count FROM User WHERE disabled = FALSE AND (validUntil IS NULL OR validUntil >= ?)`,
        new Date().toISOString()
      );
      const activeUsers = activeUsersResult.count;

      const disabledUsersResult = await db.get('SELECT COUNT(*) as count FROM User WHERE disabled = TRUE');
      const disabledUsers = disabledUsersResult.count;

      const expiredUsersResult = await db.get('SELECT COUNT(*) as count FROM User WHERE validUntil IS NOT NULL AND validUntil < ?', new Date().toISOString());
      const expiredUsers = expiredUsersResult.count;
      
      userStats = {
        total: totalUsers,
        active: activeUsers,
        disabled: disabledUsers,
        expired: expiredUsers
      };
    }

    // Group logs by user for charting
    const userTokenUsage: Record<string, Record<string, { totalTokens: number; promptTokens: number; completionTokens: number; requestCount: number }>> = {};
    
    // Initialize last 30 days for each user
    const initializeUserUsage = (userName: string) => {
      if (!userTokenUsage[userName]) {
        userTokenUsage[userName] = {};
        for (let i = 29; i >= 0; i--) {
          const date = new Date(now.getTime() - i * 24 * 60 * 60 * 1000);
          const day = `${date.getFullYear()}-${(date.getMonth() + 1).toString().padStart(2, '0')}-${date.getDate().toString().padStart(2, '0')}`;
          userTokenUsage[userName][day] = { totalTokens: 0, promptTokens: 0, completionTokens: 0, requestCount: 0 };
        }
      }
    };

    const stats: any = {
      byProvider: {},
      byChannel: {},
      byModel: {},
      byApiKey: {},
      byUser: {}, // Add user stats
      dailyUsage: [],
      weeklyUsage: [],
      monthlyUsage: [],
      userStats, // Add user statistics
      tokenUsageOverTime: [], // Add token usage over time data
      userTokenUsageOverTime: {} // Add user-specific token usage over time data
    };

    const dailyUsage: Record<string, { totalTokens: number; requestCount: number }> = {};
    const weeklyUsage: Record<string, { totalTokens: number; requestCount: number }> = {};
    const monthlyUsage: Record<string, { totalTokens: number; requestCount: number }> = {};
    const tokenUsageOverTime: Record<string, { totalTokens: number; promptTokens: number; completionTokens: number; requestCount: number }> = {};

    // Initialize last 24 hours with correct ordering
    for (let i = 23; i >= 0; i--) {
      const date = new Date(now.getTime() - i * 60 * 60 * 1000);
      const hour = `${date.getHours()}:00`;
      dailyUsage[hour] = { totalTokens: 0, requestCount: 0 };
    }

    // Initialize last 7 days with correct ordering
    for (let i = 6; i >= 0; i--) {
      const date = new Date(now.getTime() - i * 24 * 60 * 60 * 1000);
      const day = `${date.getFullYear()}-${(date.getMonth() + 1).toString().padStart(2, '0')}-${date.getDate().toString().padStart(2, '0')}`;
      weeklyUsage[day] = { totalTokens: 0, requestCount: 0 };
    }

    // Initialize last 30 days with correct ordering
    for (let i = 29; i >= 0; i--) {
      const date = new Date(now.getTime() - i * 24 * 60 * 60 * 1000);
      const day = `${date.getFullYear()}-${(date.getMonth() + 1).toString().padStart(2, '0')}-${date.getDate().toString().padStart(2, '0')}`;
      monthlyUsage[day] = { totalTokens: 0, requestCount: 0 };
      
      // Initialize token usage over time
      tokenUsageOverTime[day] = { totalTokens: 0, promptTokens: 0, completionTokens: 0, requestCount: 0 };
    }

    for (const log of logs) {
      const providerName = log.providerName;
      const channelName = log.channelName;
      const modelName = log.modelName;
      const apiKeyName = log.apiKeyName;
      const userName = log.userEmail || 'Unknown User'; // Get user email
      const date = new Date(log.createdAt);
      const day = `${date.getFullYear()}-${(date.getMonth() + 1).toString().padStart(2, '0')}-${date.getDate().toString().padStart(2, '0')}`;

      // Initialize user usage data
      initializeUserUsage(userName);

      // By Provider
      if (!stats.byProvider[providerName]) {
        stats.byProvider[providerName] = { totalTokens: 0, promptTokens: 0, completionTokens: 0, requestCount: 0 };
      }
      stats.byProvider[providerName].totalTokens += log.totalTokens;
      stats.byProvider[providerName].promptTokens += log.promptTokens;
      stats.byProvider[providerName].completionTokens += log.completionTokens;
      stats.byProvider[providerName].requestCount += 1;

      // By Channel
      if (!stats.byChannel[channelName]) {
        stats.byChannel[channelName] = { totalTokens: 0, promptTokens: 0, completionTokens: 0, requestCount: 0 };
      }
      stats.byChannel[channelName].totalTokens += log.totalTokens;
      stats.byChannel[channelName].promptTokens += log.promptTokens;
      stats.byChannel[channelName].completionTokens += log.completionTokens;
      stats.byChannel[channelName].requestCount += 1;

      // By Model
      if (!stats.byModel[modelName]) {
        stats.byModel[modelName] = { totalTokens: 0, promptTokens: 0, completionTokens: 0, requestCount: 0 };
      }
      stats.byModel[modelName].totalTokens += log.totalTokens;
      stats.byModel[modelName].promptTokens += log.promptTokens;
      stats.byModel[modelName].completionTokens += log.completionTokens;
      stats.byModel[modelName].requestCount += 1;

      // By ApiKey
      if (!stats.byApiKey[apiKeyName]) {
        stats.byApiKey[apiKeyName] = { totalTokens: 0, promptTokens: 0, completionTokens: 0, requestCount: 0 };
      }
      stats.byApiKey[apiKeyName].totalTokens += log.totalTokens;
      stats.byApiKey[apiKeyName].promptTokens += log.promptTokens;
      stats.byApiKey[apiKeyName].completionTokens += log.completionTokens;
      stats.byApiKey[apiKeyName].requestCount += 1;

      // By User (only for admin users)
      if (userRole === 'ADMIN') {
        if (!stats.byUser[userName]) {
          stats.byUser[userName] = { totalTokens: 0, promptTokens: 0, completionTokens: 0, requestCount: 0 };
        }
        stats.byUser[userName].totalTokens += log.totalTokens;
        stats.byUser[userName].promptTokens += log.promptTokens;
        stats.byUser[userName].completionTokens += log.completionTokens;
        stats.byUser[userName].requestCount += 1;
      }

      // Daily Usage (last 24 hours)
      if (date >= twentyFourHoursAgo) {
        const hour = `${date.getHours()}:00`;
        if (dailyUsage[hour]) {
          dailyUsage[hour].totalTokens += log.totalTokens;
          dailyUsage[hour].requestCount += 1;
        }
      }

      // Weekly Usage (last 7 days)
      if (weeklyUsage[day]) {
        weeklyUsage[day].totalTokens += log.totalTokens;
        weeklyUsage[day].requestCount += 1;
      }

      // Monthly Usage (last 30 days) and Token Usage Over Time
      if (monthlyUsage[day]) {
        monthlyUsage[day].totalTokens += log.totalTokens;
        monthlyUsage[day].requestCount += 1;
        
        tokenUsageOverTime[day].totalTokens += log.totalTokens;
        tokenUsageOverTime[day].promptTokens += log.promptTokens;
        tokenUsageOverTime[day].completionTokens += log.completionTokens;
        tokenUsageOverTime[day].requestCount += 1;
        
        // User-specific token usage
        userTokenUsage[userName][day].totalTokens += log.totalTokens;
        userTokenUsage[userName][day].promptTokens += log.promptTokens;
        userTokenUsage[userName][day].completionTokens += log.completionTokens;
        userTokenUsage[userName][day].requestCount += 1;
      }
    }

    stats.dailyUsage = Object.entries(dailyUsage).map(([date, data]) => ({ date, ...data }));
    stats.weeklyUsage = Object.entries(weeklyUsage).map(([date, data]) => ({ date, ...data }));
    stats.monthlyUsage = Object.entries(monthlyUsage).map(([date, data]) => ({ date, ...data }));
    stats.tokenUsageOverTime = Object.entries(tokenUsageOverTime).map(([date, data]) => ({ date, ...data }));
    
    // Convert userTokenUsage to array format for easier consumption
    stats.userTokenUsageOverTime = Object.entries(userTokenUsage).map(([userName, usageData]) => ({
      userName,
      data: Object.entries(usageData).map(([date, data]) => ({ date, ...data }))
    }));

    return NextResponse.json(stats, {
      headers: {
        'Cache-Control': 'no-store, no-cache, must-revalidate, proxy-revalidate',
        'Pragma': 'no-cache',
        'Expires': '0',
      },
    });
  } catch (error) {
    console.error("Error fetching stats:", error);
    return NextResponse.json({ error: 'An internal server error occurred.' }, { status: 500 });
  }
});