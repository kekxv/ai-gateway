import {NextResponse} from 'next/server';
import {getInitializedDb} from '@/lib/db';
import {authenticateRequest} from '../../../_lib/gateway-helpers';

export async function GET(request: Request) {
  try {
    const db = await getInitializedDb();

    const {apiKeyData: dbKey, errorResponse: authError} = await authenticateRequest(request as any, db);
    if (authError) return authError;

    // Get usage info for this specific API key
    // 1. Get total token usage and cost for this API key
    const totalUsage = await db.get(
      `SELECT SUM(promptTokens)     as     promptTokens,
              SUM(completionTokens) as completionTokens,
              SUM(totalTokens)      as      totalTokens,
              SUM(cost)             as             totalCost
       FROM Log
       WHERE apiKeyId = ?`,
      dbKey.id
    );

    // 2. Get daily usage for the last 30 days for this API key
    const thirtyDaysAgo = new Date();
    thirtyDaysAgo.setDate(thirtyDaysAgo.getDate() - 30);

    const dailyUsageResult = await db.all(
      `SELECT strftime('%Y-%m-%d', createdAt) as date, 
         SUM(totalTokens) as totalTokens,
         SUM(cost) as totalCost
       FROM Log
       WHERE apiKeyId = ?
         AND datetime(createdAt) >= datetime(?)
       GROUP BY date
       ORDER BY date ASC`,
      dbKey.id,
      thirtyDaysAgo.toISOString()
    );

    const dailyUsage = dailyUsageResult.reduce((acc: Record<string, { tokens: number; cost: number }>, curr: {
      date: string;
      totalTokens: number;
      totalCost: number
    }) => {
      acc[curr.date] = {
        tokens: Number(curr.totalTokens) || 0,
        cost: Number(curr.totalCost) || 0
      };
      return acc;
    }, {} as Record<string, { tokens: number; cost: number }>);

    // 3. Get usage per model for this API key
    const usageByModelResult = await db.all(
      `SELECT modelName,
              SUM(totalTokens) as totalTokens,
              SUM(cost)        as totalCost
       FROM Log
       WHERE apiKeyId = ?
       GROUP BY modelName
       ORDER BY totalTokens DESC`,
      dbKey.id
    );

    const usageByModel = usageByModelResult.map((item: {
      modelName: string;
      totalTokens: number;
      totalCost: number
    }) => ({
      modelName: item.modelName || 'Unknown Model',
      totalTokens: item.totalTokens || 0,
      totalCost: item.totalCost || 0,
    }));

    return NextResponse.json({
      totalUsage: {
        promptTokens: totalUsage?.promptTokens || 0,
        completionTokens: totalUsage?.completionTokens || 0,
        totalTokens: totalUsage?.totalTokens || 0,
        totalCost: totalUsage?.totalCost || 0,
      },
      dailyUsage,
      usageByModel,
    });
  } catch (error) {
    console.error('Failed to get usage info:', error);
    return NextResponse.json({error: 'Internal Server Error'}, {status: 500});
  }
}
