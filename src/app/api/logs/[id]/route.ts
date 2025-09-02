import { NextResponse } from 'next/server';
import { authMiddleware, AuthenticatedRequest } from '@/lib/auth';
import { getInitializedDb } from '@/lib/db';
import { formatTimeWithTimezone } from '@/lib/timeUtils';

export const GET = authMiddleware(async (request: AuthenticatedRequest, { params }: { params: { id: string } }) => {
  try {
    const userId = request.user?.userId;
    const userRole = request.user?.role;

    const db = await getInitializedDb();

    let query = `SELECT l.*, ld.requestBody, ld.responseBody, ak.name as apiKeyName, ak.userId as apiKeyUserId, u.email as userEmail, u.role as userRole, c.id as ownerChannelId, c.name as ownerChannelName, cu.email as ownerChannelUserEmail
                 FROM Log l
                 LEFT JOIN LogDetail ld ON l.id = ld.logId
                 JOIN GatewayApiKey ak ON l.apiKeyId = ak.id
                 LEFT JOIN User u ON ak.userId = u.id
                 LEFT JOIN Channel c ON l.ownerChannelId = c.id
                 LEFT JOIN User cu ON l.ownerChannelUserId = cu.id
                 WHERE l.id = ?`;

    const queryParams: any[] = [params.id];

    if (userRole !== 'ADMIN') {
      query += ` AND ak.userId = ?`;
      queryParams.push(userId);
    }

    const log = await db.get(query, ...queryParams);

    if (!log) {
      return NextResponse.json({ error: 'Log not found' }, { status: 404 });
    }

    const formattedLog = {
      id: log.id,
      createdAt: formatTimeWithTimezone(log.createdAt),
      latency: log.latency,
      promptTokens: log.promptTokens,
      completionTokens: log.completionTokens,
      totalTokens: log.totalTokens,
      cost: log.cost,
      logDetail: (log.requestBody || log.responseBody) ? {
        requestBody: log.requestBody,
        responseBody: log.responseBody,
      } : null,
      apiKey: log.apiKeyName ? {
        name: log.apiKeyName,
        user: log.userEmail ? {
          email: log.userEmail,
          role: log.userRole,
        } : undefined,
      } : undefined,
      modelName: log.modelName,
      providerName: log.providerName,
      ownerChannel: log.ownerChannelId ? {
        id: log.ownerChannelId,
        name: log.ownerChannelName,
        user: log.ownerChannelUserEmail ? {
          email: log.ownerChannelUserEmail
        } : undefined
      } : undefined
    };

    return NextResponse.json(formattedLog, {
      headers: {
        'Cache-Control': 'no-store, no-cache, must-revalidate, proxy-revalidate',
        'Pragma': 'no-cache',
        'Expires': '0',
      },
    });
  } catch (error) {
    console.error("Error fetching log details:", error);
    return NextResponse.json({ error: 'An internal server error occurred.' }, { status: 500 });
  }
});