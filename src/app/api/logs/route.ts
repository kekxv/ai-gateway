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

    let whereClause: any = {};
    if (userRole !== 'ADMIN') {
      whereClause = {
        apiKey: {
          userId: userId,
        },
      };
    }

    const db = await getInitializedDb();

    let query = `SELECT l.*, ld.requestBody, ld.responseBody, ak.name as apiKeyName, ak.userId as apiKeyUserId, u.email as userEmail, u.role as userRole, mr.modelId, mr.channelId, m.name as modelName, c.name as channelName
                 FROM Log l
                 LEFT JOIN LogDetail ld ON l.id = ld.logId
                 JOIN GatewayApiKey ak ON l.apiKeyId = ak.id
                 LEFT JOIN User u ON ak.userId = u.id
                 JOIN ModelRoute mr ON l.modelRouteId = mr.id
                 JOIN Model m ON mr.modelId = m.id
                 JOIN Channel c ON mr.channelId = c.id`;

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

    // Manually structure the data to match Prisma's output format
    const formattedLogs = logs.map((log: any) => ({
      id: log.id,
      createdAt: log.createdAt,
      latency: log.latency,
      promptTokens: log.promptTokens,
      completionTokens: log.completionTokens,
      totalTokens: log.totalTokens,
      logDetail: (log.requestBody || log.responseBody) ? {
        requestBody: log.requestBody,
        responseBody: log.responseBody,
      } : null,
      apiKey: log.apiKeyName ? {
        name: log.apiKeyName,
        user: log.userEmail ? {
          email: log.userEmail,
          role: log.userRole,
        } : undefined, // 如果没有用户，设置为 undefined
      } : undefined, // 如果没有 apiKeyName，设置为 undefined
      modelRoute: {
        model: {
          name: log.modelName,
        },
        channel: {
          name: log.channelName,
        },
      },
    }));
    console.log(`Total logs: ${totalLogs}, Limit: ${limit}`); // Add console.log
    console.log('Logs data sent to frontend:', JSON.stringify(formattedLogs, null, 2)); // Add this line

    return NextResponse.json({
      logs: formattedLogs, // Use formattedLogs here
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