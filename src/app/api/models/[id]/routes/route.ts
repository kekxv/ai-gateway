import { NextResponse } from 'next/server';
import { authMiddleware, AuthenticatedRequest } from '@/lib/auth';
import { getInitializedDb } from '@/lib/db';

// GET /api/models/[id]/routes - Fetches all routes for a model
export const GET = authMiddleware(async (request: AuthenticatedRequest, context: { params: Promise<{ id: string }> }) => {
  try {
    const params = await context.params;
    const { id } = params;
    const modelId = parseInt(id, 10);
    const userId = request.user?.userId;
    const userRole = request.user?.role;

    if (isNaN(modelId)) {
      return NextResponse.json({ error: '无效的模型 ID' }, { status: 400 });
    }

    const db = await getInitializedDb();
    
    // Check if the model exists and user has permission
    const model = await db.get(
      `SELECT * FROM Model WHERE id = ? ${userRole !== 'ADMIN' ? 'AND userId = ?' : ''}`,
      modelId,
      ...(userRole !== 'ADMIN' ? [userId] : [])
    );
    
    if (!model) {
      return NextResponse.json({ error: '模型未找到或无权限访问' }, { status: 404 });
    }
    
    // Get query parameters
    const { searchParams } = new URL(request.url);
    const providerId = searchParams.get('providerId');
    
    // Fetch model routes
    let routes;
    if (providerId) {
      routes = await db.all(
        'SELECT * FROM ModelRoute WHERE modelId = ? AND providerId = ?',
        modelId,
        parseInt(providerId, 10)
      );
    } else {
      routes = await db.all('SELECT * FROM ModelRoute WHERE modelId = ?', modelId);
    }
    
    return NextResponse.json(routes, { status: 200 });
  } catch (error) {
    console.error("Error fetching model routes:", error);
    return NextResponse.json({ error: '获取模型路由失败' }, { status: 500 });
  }
});