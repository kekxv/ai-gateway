import { NextResponse } from 'next/server';
import { PrismaClient } from '@prisma/client';
import { authMiddleware, AuthenticatedRequest } from '@/lib/auth';

const prisma = new PrismaClient();

// GET /api/models - Fetches all models
export const GET = authMiddleware(async (request: AuthenticatedRequest) => {
  try {
    const userId = request.user?.userId;
    const userRole = request.user?.role;

    let whereClause = {};
    if (userRole !== 'ADMIN') {
      whereClause = { userId: userId };
    }

    const models = await prisma.model.findMany({
      where: whereClause,
      include: {
        user: true,
        modelRoutes: { // NEW: Include modelRoutes
          include: {
            channel: {
              include: {
                provider: true, // Include provider for channel for display purposes in frontend
              },
            },
          },
        },
        providerModels: true, // Include providerModels for filtering in frontend
      },
      orderBy: {
        createdAt: 'desc',
      },
    });
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

    // Batch creation logic
    if (Array.isArray(models) && providerId) {
      const createdModels = [];
      for (const modelData of models) {
        const existingModel = await prisma.model.findUnique({
          where: { name: modelData.name },
        });

        let modelId: number;

        if (!existingModel) {
          const newModel = await prisma.model.create({
            data: {
              name: modelData.name,
              description: modelData.description,
              user: { connect: { id: userId } },
            },
          });
          modelId = newModel.id;
          createdModels.push(newModel);
        } else {
          modelId = existingModel.id;
        }

        // Associate model with the provider if not already associated
        const existingProviderModel = await prisma.providerModel.findUnique({
          where: { providerId_modelId: { providerId, modelId } },
        });

        if (!existingProviderModel) {
          await prisma.providerModel.create({
            data: { providerId, modelId },
          });
        }
      }
      return NextResponse.json({ message: `成功添加 ${createdModels.length} 个新模型`, createdModels }, { status: 201 });
    }

    // Single creation logic
    if (name) {
      const newModel = await prisma.model.create({
        data: {
          name,
          description,
          user: { connect: { id: userId } },
          modelRoutes: {
            create: modelRoutes ? modelRoutes.map((route: { channelId: number, weight: number }) => ({
              channel: { connect: { id: route.channelId } },
              weight: route.weight,
            })) : [],
          },
        },
      });
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
