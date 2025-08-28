import { NextResponse } from 'next/server';
import { PrismaClient } from '@prisma/client';
import { authMiddleware, AuthenticatedRequest } from '@/lib/auth'; // Import authMiddleware

const prisma = new PrismaClient();

// PUT /api/models/[id] - Updates a model
export const PUT = authMiddleware(async (request: AuthenticatedRequest, context: { params: { id: string } }) => {
  try {
    const { id: paramId } = await context.params;
    const id = parseInt(paramId);
    const userId = request.user?.userId;
    const userRole = request.user?.role;

    if (isNaN(id)) {
      return NextResponse.json({ error: '缺少模型 ID 或无效的 ID' }, { status: 400 });
    }

    // Check ownership or admin role
    const existingModel = await prisma.model.findUnique({ where: { id: id } });
    if (!existingModel) {
      return NextResponse.json({ error: '模型未找到' }, { status: 404 });
    }
    if (userRole !== 'ADMIN' && existingModel.userId !== userId) {
      return NextResponse.json({ error: '无权更新此模型' }, { status: 403 });
    }

    const body = await request.json();
    const { name, description, modelRoutes, newUserId } = body; // UPDATED: modelRoutes instead of providerIds

    // Validate newUserId if provided and user is admin
    if (newUserId !== undefined && userRole !== 'ADMIN') {
      return NextResponse.json({ error: '无权更改模型所有者' }, { status: 403 });
    }
    if (newUserId !== undefined) {
      const targetUser = await prisma.user.findUnique({ where: { id: newUserId } });
      if (!targetUser) {
        return NextResponse.json({ error: '目标用户不存在' }, { status: 400 });
      }
    }

    // --- Start: ModelRoute Management ---
    // 1. Delete all existing ModelRoutes for this model
    await prisma.modelRoute.deleteMany({
      where: { modelId: id },
    });

    // 2. Create new ModelRoutes based on the received array
    const updateData: any = {
      name,
      description,
      modelRoutes: {
        create: modelRoutes ? modelRoutes.map((route: { channelId: number, weight: number }) => ({
          channel: { connect: { id: route.channelId } },
          weight: route.weight,
        })) : [],
      },
    };

    if (newUserId !== undefined) {
      updateData.user = { connect: { id: newUserId } };
    }

    const updatedModel = await prisma.model.update({
      where: { id: id },
      data: updateData,
    });

    return NextResponse.json(updatedModel);
  } catch (error) {
    console.error("Error updating model:", error);
    if (error instanceof Error && 'code' in error && (error as { code: string }).code === 'P2002') {
      return NextResponse.json({ error: '此名称的模型已存在' }, { status: 409 });
    }
    return NextResponse.json({ error: '更新模型失败' }, { status: 500 });
  }
});

// DELETE /api/models/[id] - Deletes a model
export const DELETE = authMiddleware(async (request: AuthenticatedRequest, context: { params: { id: string } }) => {
  try {
    const { id: paramId } = await context.params;
    const id = parseInt(paramId);
    const userId = request.user?.userId;
    const userRole = request.user?.role;

    if (isNaN(id)) {
      return NextResponse.json({ error: '缺少模型 ID 或无效的 ID' }, { status: 400 });
    }

    // Check ownership or admin role
    const existingModel = await prisma.model.findUnique({ where: { id: id } });
    if (!existingModel) {
      return NextResponse.json({ error: '模型未找到' }, { status: 404 });
    }
    if (userRole !== 'ADMIN' && existingModel.userId !== userId) {
      return NextResponse.json({ error: '无权删除此模型' }, { status: 403 });
    }

    await prisma.model.delete({
      where: { id: id },
    });

    return NextResponse.json({ message: '模型删除成功' });
  } catch (error) {
    console.error("Error deleting model:", error);
    return NextResponse.json({ error: '删除模型失败' }, { status: 500 });
  }
});
