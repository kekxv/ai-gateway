import { NextResponse } from 'next/server';
import { authMiddleware, AuthenticatedRequest } from '@/lib/auth';
import { getInitializedDb } from '@/lib/db';

async function getUserStats(req: AuthenticatedRequest) {
  try {
    const userId = req.user?.userId;
    if (!userId) {
      return NextResponse.json({ error: '令牌中未找到用户' }, { status: 400 });
    }

    const db = await getInitializedDb();

    // Find all ApiKey IDs for the current user
    const userApiKeys = await db.all(
      'SELECT id FROM GatewayApiKey WHERE userId = ?',
      userId
    );
    const apiKeyIds = userApiKeys.map((k: { id: number }) => k.id);

    if (apiKeyIds.length === 0) {
      // If user has no keys, they have no usage
      return NextResponse.json({
        totalUsage: { promptTokens: 0, completionTokens: 0, totalTokens: 0 },
        dailyUsage: {},
        usageByModel: [],
      });
    }

    // 1. Get total token usage
    const totalUsage = await db.get(
      `SELECT SUM(promptTokens) as promptTokens, SUM(completionTokens) as completionTokens, SUM(totalTokens) as totalTokens
       FROM Log
       WHERE apiKeyId IN (${apiKeyIds.map(() => '?').join(',')})`,
      ...apiKeyIds
    );

    // 2. Get daily usage for the last 30 days using raw SQL for date grouping
    const thirtyDaysAgo = new Date();
    thirtyDaysAgo.setDate(thirtyDaysAgo.getDate() - 30);

    const dailyUsageResult = await db.all(
      `SELECT strftime('%Y-%m-%d', createdAt) as date, SUM(totalTokens) as total
       FROM Log
       WHERE apiKeyId IN (${apiKeyIds.map(() => '?').join(',')})
       AND datetime(createdAt) >= datetime(?)
       GROUP BY date
       ORDER BY date ASC`,
      ...apiKeyIds,
      thirtyDaysAgo.toISOString()
    );

    const dailyUsage = dailyUsageResult.reduce((acc: Record<string, number>, curr: { date: string; total: number }) => {
      acc[curr.date] = Number(curr.total);
      return acc;
    }, {} as Record<string, number>);

    // 3. Get usage per model
    const usageByModelResult = await db.all(
      `SELECT modelName, SUM(totalTokens) as totalTokens, SUM(cost) as totalCost
       FROM Log
       WHERE apiKeyId IN (${apiKeyIds.map(() => '?').join(',')})
       GROUP BY modelName`,
      ...apiKeyIds
    );

    const usageByModel = usageByModelResult.map((item: { modelName: string; totalTokens: number; totalCost: number }) => ({
      modelName: item.modelName || '未知模型',
      totalTokens: item.totalTokens || 0,
      totalCost: item.totalCost || 0,
    })).sort((a: { modelName: string; totalTokens: number }, b: { modelName: string; totalTokens: number }) => b.totalTokens - a.totalTokens); // Sort by most used


    return NextResponse.json({
      totalUsage: {
        promptTokens: totalUsage?.promptTokens || 0,
        completionTokens: totalUsage?.completionTokens || 0,
        totalTokens: totalUsage?.totalTokens || 0,
      },
      dailyUsage,
      usageByModel,
    });
  } catch (error) {
    console.error('获取用户统计失败:', error);
    return NextResponse.json({ error: '服务器内部错误' }, { status: 500 });
  }
}

export const GET = authMiddleware(getUserStats);
