import { NextResponse } from 'next/server';
import { authMiddleware, AuthenticatedRequest } from '@/lib/auth';
import { getInitializedDb } from '@/lib/db';

// POST /api/model-routes - Creates a new model route
export const POST = authMiddleware(async (request: AuthenticatedRequest) => {
  try {
    const userId = request.user?.userId;
    if (!userId) {
      return NextResponse.json({ error: '未授权: 用户ID缺失' }, { status: 401 });
    }

    const body = await request.json();
    const { modelId, providerId, weight = 1 } = body;

    if (!modelId || !providerId) {
      return NextResponse.json({ error: '缺少必填字段: modelId 和 providerId' }, { status: 400 });
    }

    const db = await getInitializedDb();
    
    // Check if the model exists
    const model = await db.get('SELECT * FROM Model WHERE id = ?', modelId);
    if (!model) {
      return NextResponse.json({ error: '模型未找到' }, { status: 404 });
    }
    
    // Check if the provider exists
    const provider = await db.get('SELECT * FROM Provider WHERE id = ?', providerId);
    if (!provider) {
      return NextResponse.json({ error: '提供商未找到' }, { status: 404 });
    }
    
    // Check if a ModelRoute already exists for this model and provider
    const existingRoute = await db.get(
      'SELECT * FROM ModelRoute WHERE modelId = ? AND providerId = ?',
      modelId,
      providerId
    );
    
    if (existingRoute) {
      return NextResponse.json({ error: '该模型路由已存在' }, { status: 409 });
    }
    
    // Create the new ModelRoute
    const result = await db.run(
      'INSERT INTO ModelRoute (modelId, providerId, weight) VALUES (?, ?, ?)',
      modelId,
      providerId,
      weight
    );
    
    const newRoute = await db.get('SELECT * FROM ModelRoute WHERE id = ?', result.lastID);
    
    return NextResponse.json(newRoute, { status: 201 });
  } catch (error) {
    console.error("Error creating model route:", error);
    return NextResponse.json({ error: '创建模型路由失败' }, { status: 500 });
  }
});