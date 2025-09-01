import { NextResponse } from 'next/server';
import { authMiddleware, AuthenticatedRequest } from '@/lib/auth'; // Import authMiddleware
import { getInitializedDb } from '@/lib/db';

export const GET = authMiddleware(async (request: AuthenticatedRequest) => {
  const { searchParams } = new URL(request.url);
  const page = parseInt(searchParams.get('page') || '1', 10);
  const limit = parseInt(searchParams.get('limit') || '10', 10);
  const skip = (page - 1) * limit;

  try {
    const userId = request.user?.userId;
    const userRole = request.user?.role;

    const db = await getInitializedDb();

    let query = `SELECT l.*, ld.requestBody, ld.responseBody, ak.name as apiKeyName, ak.userId as apiKeyUserId, u.email as userEmail, u.role as userRole
                 FROM Log l
                 LEFT JOIN LogDetail ld ON l.id = ld.logId
                 JOIN GatewayApiKey ak ON l.apiKeyId = ak.id
                 LEFT JOIN User u ON ak.userId = u.id`;

    let countQuery = `SELECT COUNT(*) as count FROM Log l JOIN GatewayApiKey ak ON l.apiKeyId = ak.id`;

    const queryParams: any[] = [];
    const countQueryParams: any[] = [];

    if (userRole !== 'ADMIN') {
      query += ` WHERE ak.userId = ?`;
      countQuery += ` WHERE ak.userId = ?`;
      queryParams.push(userId);
      countQueryParams.push(userId);
    }

    query += ` ORDER BY l.createdAt DESC LIMIT ? OFFSET ?`;
    queryParams.push(limit, skip);

    const logs = await db.all(query, ...queryParams);

    const totalLogsResult = await db.get(countQuery, ...countQueryParams);
    const totalLogs = totalLogsResult.count;

    const formattedLogs = logs.map((log: any) => ({
      id: log.id,
      createdAt: log.createdAt,
      latency: log.latency,
      promptTokens: log.promptTokens,
      completionTokens: log.completionTokens,
      totalTokens: log.totalTokens,
      cost: log.cost, // Add this line
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
    }));

    return NextResponse.json({
      logs: formattedLogs,
      totalPages: Math.ceil(totalLogs / limit),
      currentPage: page,
    }, {
      headers: {
        'Cache-Control': 'no-store, no-cache, must-revalidate, proxy-revalidate',
        'Pragma': 'no-cache',
        'Expires': '0',
      },
    });
  } catch (error) {
    console.error("Error fetching logs:", error);
    return NextResponse.json({ error: 'An internal server error occurred.' }, { status: 500 });
  }
});
