import { NextResponse } from 'next/server';
import { authMiddleware, AuthenticatedRequest } from '@/lib/auth';
import { getInitializedDb } from '@/lib/db';

export const GET = authMiddleware(async (request: AuthenticatedRequest) => {
  try {
    const now = new Date();
    const twentyFourHoursAgo = new Date(now.getTime() - 24 * 60 * 60 * 1000);
    const sevenDaysAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
    const thirtyDaysAgo = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);

    const userId = request.user?.userId;
    const userRole = request.user?.role;

    const db = await getInitializedDb();

    let logQuery = `
      SELECT
        l.id, l.latency, l.promptTokens, l.completionTokens, l.totalTokens, l.createdAt, l.cost,
        ak.name AS apiKeyName, ak.userId AS apiKeyUserId,
        u.email AS userEmail, u.role AS userRole,
        l.modelName,
        l.providerName
      FROM Log l
      JOIN GatewayApiKey ak ON l.apiKeyId = ak.id
      LEFT JOIN User u ON ak.userId = u.id
      WHERE l.createdAt >= ?
    `;
    const logQueryParams: any[] = [thirtyDaysAgo.toISOString()];

    if (userRole !== 'ADMIN') {
      logQuery += ` AND ak.userId = ?`;
      logQueryParams.push(userId);
    }

    logQuery += ` ORDER BY l.createdAt ASC`;

    const logs = await db.all(logQuery, ...logQueryParams);

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

    const userTokenUsage: Record<string, Record<string, { totalTokens: number; promptTokens: number; completionTokens: number; requestCount: number }>> = {};
    
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
      byModel: {},
      byApiKey: {},
      byUser: {},
      dailyUsage: [],
      weeklyUsage: [],
      monthlyUsage: [],
      userStats,
      tokenUsageOverTime: [],
      userTokenUsageOverTime: {},
      totalCost: 0, // Initialize totalCost
    };

    const dailyUsage: Record<string, { totalTokens: number; requestCount: number }> = {};
    const weeklyUsage: Record<string, { totalTokens: number; requestCount: number }> = {};
    const monthlyUsage: Record<string, { totalTokens: number; requestCount: number }> = {};
    const tokenUsageOverTime: Record<string, { totalTokens: number; promptTokens: number; completionTokens: number; requestCount: number }> = {};

    for (let i = 23; i >= 0; i--) {
      const date = new Date(now.getTime() - i * 60 * 60 * 1000);
      const hour = `${date.getHours()}:00`;
      dailyUsage[hour] = { totalTokens: 0, requestCount: 0 };
    }

    for (let i = 6; i >= 0; i--) {
      const date = new Date(now.getTime() - i * 24 * 60 * 60 * 1000);
      const day = `${date.getFullYear()}-${(date.getMonth() + 1).toString().padStart(2, '0')}-${date.getDate().toString().padStart(2, '0')}`;
      weeklyUsage[day] = { totalTokens: 0, requestCount: 0 };
    }

    for (let i = 29; i >= 0; i--) {
      const date = new Date(now.getTime() - i * 24 * 60 * 60 * 1000);
      const day = `${date.getFullYear()}-${(date.getMonth() + 1).toString().padStart(2, '0')}-${date.getDate().toString().padStart(2, '0')}`;
      monthlyUsage[day] = { totalTokens: 0, requestCount: 0 };
      tokenUsageOverTime[day] = { totalTokens: 0, promptTokens: 0, completionTokens: 0, requestCount: 0 };
    }

    for (const log of logs) {
      const providerName = log.providerName;
      const modelName = log.modelName;
      const apiKeyName = log.apiKeyName;
      const userName = log.userEmail || 'Unknown User';
      const date = new Date(log.createdAt);
      const day = `${date.getFullYear()}-${(date.getMonth() + 1).toString().padStart(2, '0')}-${date.getDate().toString().padStart(2, '0')}`;

      initializeUserUsage(userName);

      stats.totalCost += log.cost; // Accumulate total cost

      if (providerName) {
        if (!stats.byProvider[providerName]) {
          stats.byProvider[providerName] = { totalTokens: 0, promptTokens: 0, completionTokens: 0, requestCount: 0, cost: 0 }; // Add cost
        }
        stats.byProvider[providerName].totalTokens += log.totalTokens;
        stats.byProvider[providerName].promptTokens += log.promptTokens;
        stats.byProvider[providerName].completionTokens += log.completionTokens;
        stats.byProvider[providerName].requestCount += 1;
        stats.byProvider[providerName].cost += log.cost; // Add cost
      }

      if (modelName) {
        if (!stats.byModel[modelName]) {
          stats.byModel[modelName] = { totalTokens: 0, promptTokens: 0, completionTokens: 0, requestCount: 0, cost: 0 }; // Add cost
        }
        stats.byModel[modelName].totalTokens += log.totalTokens;
        stats.byModel[modelName].promptTokens += log.promptTokens;
        stats.byModel[modelName].completionTokens += log.completionTokens;
        stats.byModel[modelName].requestCount += 1;
        stats.byModel[modelName].cost += log.cost; // Add cost
      }

      if (apiKeyName) {
        if (!stats.byApiKey[apiKeyName]) {
          stats.byApiKey[apiKeyName] = { totalTokens: 0, promptTokens: 0, completionTokens: 0, requestCount: 0, cost: 0 }; // Add cost
        }
        stats.byApiKey[apiKeyName].totalTokens += log.totalTokens;
        stats.byApiKey[apiKeyName].promptTokens += log.promptTokens;
        stats.byApiKey[apiKeyName].completionTokens += log.completionTokens;
        stats.byApiKey[apiKeyName].requestCount += 1;
        stats.byApiKey[apiKeyName].cost += log.cost; // Add cost
      }

      if (userRole === 'ADMIN' && userName) {
        if (!stats.byUser[userName]) {
          stats.byUser[userName] = { totalTokens: 0, promptTokens: 0, completionTokens: 0, requestCount: 0, cost: 0 }; // Add cost
        }
        stats.byUser[userName].totalTokens += log.totalTokens;
        stats.byUser[userName].promptTokens += log.promptTokens;
        stats.byUser[userName].completionTokens += log.completionTokens;
        stats.byUser[userName].requestCount += 1;
        stats.byUser[userName].cost += log.cost; // Add cost
      }

      if (date >= twentyFourHoursAgo) {
        const hour = `${date.getHours()}:00`;
        if (dailyUsage[hour]) {
          dailyUsage[hour].totalTokens += log.totalTokens;
          dailyUsage[hour].requestCount += 1;
        }
      }

      if (weeklyUsage[day]) {
        weeklyUsage[day].totalTokens += log.totalTokens;
        weeklyUsage[day].requestCount += 1;
      }

      if (monthlyUsage[day]) {
        monthlyUsage[day].totalTokens += log.totalTokens;
        monthlyUsage[day].requestCount += 1;
        
        tokenUsageOverTime[day].totalTokens += log.totalTokens;
        tokenUsageOverTime[day].promptTokens += log.promptTokens;
        tokenUsageOverTime[day].completionTokens += log.completionTokens;
        tokenUsageOverTime[day].requestCount += 1;
        
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