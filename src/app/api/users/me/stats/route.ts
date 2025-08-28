import { NextResponse } from 'next/server';
import { authMiddleware, AuthenticatedRequest } from '@/lib/auth';
import { Prisma, PrismaClient } from '@prisma/client';

const prisma = new PrismaClient();

async function getUserStats(req: AuthenticatedRequest) {
  try {
    const userId = req.user?.userId;
    if (!userId) {
      return NextResponse.json({ error: '令牌中未找到用户' }, { status: 400 });
    }

    // Find all ApiKey IDs for the current user
    const userApiKeys = await prisma.gatewayApiKey.findMany({
      where: { userId: userId },
      select: { id: true },
    });
    const apiKeyIds = userApiKeys.map(k => k.id);

    if (apiKeyIds.length === 0) {
      // If user has no keys, they have no usage
      return NextResponse.json({
        totalUsage: { promptTokens: 0, completionTokens: 0, totalTokens: 0 },
        dailyUsage: {},
        usageByModel: [],
      });
    }

    // 1. Get total token usage
    const totalUsage = await prisma.log.aggregate({
      _sum: {
        promptTokens: true,
        completionTokens: true,
        totalTokens: true,
      },
      where: {
        apiKeyId: { in: apiKeyIds },
      },
    });

    // 2. Get daily usage for the last 30 days using raw SQL for date grouping
    const thirtyDaysAgo = new Date();
    thirtyDaysAgo.setDate(thirtyDaysAgo.getDate() - 30);

    const dailyUsageResult: { date: string; total: bigint }[] = await prisma.$queryRaw`
      SELECT strftime('%Y-%m-%d', datetime(createdAt / 1000, 'unixepoch')) as date, SUM(totalTokens) as total
      FROM Log
      WHERE apiKeyId IN (${Prisma.join(apiKeyIds)})
      AND createdAt >= ${thirtyDaysAgo.getTime()}
      GROUP BY date
      ORDER BY date ASC
    `;

    const dailyUsage = dailyUsageResult.reduce((acc, curr) => {
      acc[curr.date] = Number(curr.total);
      return acc;
    }, {} as Record<string, number>);

    // 3. Get usage per model
    const usageByModelResult = await prisma.log.groupBy({
      by: ['modelRouteId'],
      _sum: {
        totalTokens: true,
      },
      where: {
        apiKeyId: { in: apiKeyIds },
      },
    });

    const modelRouteIds = usageByModelResult.map(item => item.modelRouteId);
    const modelRoutes = await prisma.modelRoute.findMany({
      where: {
        id: { in: modelRouteIds },
      },
      select: { id: true, model: { select: { name: true } } },
    });

    const modelIdToNameMap = modelRoutes.reduce((acc, route) => {
      acc[route.id] = route.model.name;
      return acc;
    }, {} as Record<number, string>);

    const usageByModel = usageByModelResult.map(item => ({
      modelName: modelIdToNameMap[item.modelRouteId] || '未知模型',
      totalTokens: item._sum.totalTokens || 0,
    })).sort((a, b) => b.totalTokens - a.totalTokens); // Sort by most used


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
