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
      `SELECT strftime('%Y-%m-%d', datetime(createdAt / 1000, 'unixepoch')) as date, SUM(totalTokens) as total
       FROM Log
       WHERE apiKeyId IN (${apiKeyIds.map(() => '?').join(',')})
       AND createdAt >= ?
       GROUP BY date
       ORDER BY date ASC`,
      ...apiKeyIds,
      thirtyDaysAgo.getTime()
    );

    const dailyUsage = dailyUsageResult.reduce((acc: Record<string, number>, curr: { date: string; total: number }) => {
      acc[curr.date] = Number(curr.total);
      return acc;
    }, {} as Record<string, number>);

    // 3. Get usage per model
    const usageByModelResult = await db.all(
      `SELECT modelRouteId, SUM(totalTokens) as totalTokens
       FROM Log
       WHERE apiKeyId IN (${apiKeyIds.map(() => '?').join(',')})
       GROUP BY modelRouteId`,
      ...apiKeyIds
    );

    const modelRouteIds = usageByModelResult.map((item: { modelRouteId: number; totalTokens: number }) => item.modelRouteId);
    const modelRoutes = await db.all(
      `SELECT id, modelId FROM ModelRoute WHERE id IN (${modelRouteIds.map(() => '?').join(',')})`,
      ...modelRouteIds
    );

    const modelIdToNameMap: Record<number, string> = {};
    for (const route of modelRoutes) {
      const model = await db.get('SELECT name FROM Model WHERE id = ?', route.modelId);
      if (model) {
        modelIdToNameMap[route.id] = model.name;
      }
    }

    const usageByModel = usageByModelResult.map((item: { modelRouteId: number; totalTokens: number }) => ({
      modelName: modelIdToNameMap[item.modelRouteId] || '未知模型',
      totalTokens: item.totalTokens || 0,
    })).sort((a: { modelName: string; totalTokens: number }, b: { modelName: string; totalTokens: number }) => b.totalTokens - a.totalTokens); // Sort by most used


    return NextResponse.json({
      totalUsage: {
        promptTokens: totalUsage._sum.promptTokens || 0,
        completionTokens: totalUsage._sum.completionTokens || 0,
        totalTokens: totalUsage._sum.totalTokens || 0,
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
