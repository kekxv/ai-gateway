import { NextResponse } from 'next/server';
import { authMiddleware, AuthenticatedRequest } from '@/lib/auth';
import { getInitializedDb } from '@/lib/db';

// GET /api/models - Fetches all models
export const GET = authMiddleware(async (request: AuthenticatedRequest) => {
  try {
    const userId = request.user?.userId;
    const userRole = request.user?.role;

    let whereClause = {};
    if (userRole !== 'ADMIN') {
      whereClause = { userId: userId };
    }

    const db = await getInitializedDb();

    const models = await db.all(
      `SELECT * FROM Model ${userRole !== 'ADMIN' ? 'WHERE userId = ?' : ''} ORDER BY createdAt DESC`,
      ...(userRole !== 'ADMIN' ? [userId] : [])
    );

    for (const model of models) {
      if (model.userId) {
        model.user = await db.get('SELECT id, email, role FROM User WHERE id = ?', model.userId);
      }
      model.modelRoutes = await db.all(
        `SELECT mr.*, c.name as channelName, p.name as providerName
         FROM ModelRoute mr
         JOIN Channel c ON mr.channelId = c.id
         JOIN Provider p ON c.providerId = p.id
         WHERE mr.modelId = ?`,
        model.id
      );
      model.providerModels = await db.all(
        'SELECT * FROM ProviderModel WHERE modelId = ?',
        model.id
      );
    }
    return NextResponse.json(models, {
      headers: {
        'Cache-Control': 'no-store, no-cache, must-revalidate, proxy-revalidate',
        'Pragma': 'no-cache',
        'Expires': '0',
      },
    });
  } catch (error) {
    console.error("Error fetching models:", error);
    return NextResponse.json({ error: '获取模型失败' }, { status: 500 });
  }
});

// POST /api/models - Creates one or more models and associates them with a provider
export const POST = authMiddleware(async (request: AuthenticatedRequest) => {
  try {
    const userId = request.user?.userId;
    if (!userId) {
      return NextResponse.json({ error: '未授权: 用户ID缺失' }, { status: 401 });
    }

    const body = await request.json();
    const { models, providerId } = body; // For batch creation from model selection modal
    const { name, description, modelRoutes } = body; // For single model creation from form

    const db = await getInitializedDb();

    // Batch creation logic
    if (Array.isArray(models) && providerId) {
      const createdModels = [];
      for (const modelData of models) {
        const existingModel = await db.get('SELECT * FROM Model WHERE name = ?', modelData.name);

        let modelId: number;

        if (!existingModel) {
          const result = await db.run(
            'INSERT INTO Model (name, description, userId) VALUES (?, ?, ?)',
            modelData.name,
            modelData.description,
            userId
          );
          modelId = result.lastID;
          createdModels.push({ id: modelId, name: modelData.name, description: modelData.description });
        } else {
          modelId = existingModel.id;
        }

        // Associate model with the provider if not already associated
        const existingProviderModel = await db.get(
          'SELECT * FROM ProviderModel WHERE providerId = ? AND modelId = ?',
          providerId,
          modelId
        );

        if (!existingProviderModel) {
          await db.run(
            'INSERT INTO ProviderModel (providerId, modelId) VALUES (?, ?)',
            providerId,
            modelId
          );
        }
      }
      return NextResponse.json({ message: `成功添加 ${createdModels.length} 个新模型`, createdModels }, { status: 201 });
    }

    // Single creation logic
    if (name) {
      const result = await db.run(
        'INSERT INTO Model (name, description, userId) VALUES (?, ?, ?)',
        name,
        description,
        userId
      );
      const newModelId = result.lastID;

      if (modelRoutes && modelRoutes.length > 0) {
        for (const route of modelRoutes) {
          await db.run(
            'INSERT INTO ModelRoute (modelId, channelId, weight) VALUES (?, ?, ?)',
            newModelId,
            route.channelId,
            route.weight
          );
        }
      }
      const newModel = await db.get('SELECT * FROM Model WHERE id = ?', newModelId);
      return NextResponse.json(newModel, { status: 201 });
    }

    return NextResponse.json({ error: '无效的请求体' }, { status: 400 });

  } catch (error) {
    console.error("Error creating model:", error);
    if (error instanceof Error && 'code' in error && (error as { code: string }).code === 'P2002') {
      return NextResponse.json({ error: '一个或多个模型名称已存在' }, { status: 409 });
    }
    return NextResponse.json({ error: '创建模型失败' }, { status: 500 });
  }
});
