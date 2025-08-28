import { NextResponse } from 'next/server';
import { PrismaClient } from '@prisma/client';
import { AuthenticatedRequest } from '@/lib/auth'; // Import authMiddleware

const prisma = new PrismaClient();

export async function GET(request: AuthenticatedRequest, context: { params: Promise<{ id: string }> }) {
  try {
    const params = await context.params;
    const id = parseInt(params.id);
    const userId = request.user?.userId;
    const userRole = request.user?.role;

    if (isNaN(id)) {
      return NextResponse.json({ error: '无效的 ID' }, { status: 400 });
    }

    let whereClause: any = { id: id };
    if (userRole !== 'ADMIN') {
      whereClause = { ...whereClause, userId: userId };
    }

    const channel = await prisma.channel.findUnique({
      where: whereClause,
      include: {
        provider: true,
        modelRoutes: {
          include: {
            model: true,
          },
        },
      },
    });

    if (!channel) {
      return NextResponse.json({ error: '渠道未找到或无权访问' }, { status: 404 });
    }

    return NextResponse.json(channel);
  } catch (error) {
    console.error("Error fetching channel:", error);
    return NextResponse.json({ error: '获取渠道失败' }, { status: 500 });
  }
}

// PUT /api/channels/[id] - Updates a channel
export async function PUT(request: AuthenticatedRequest, context: { params: Promise<{ id: string }> }) {
  try {
    const params = await context.params;
    const id = parseInt(params.id);
    const userId = request.user?.userId;
    const userRole = request.user?.role;

    if (isNaN(id)) {
      return NextResponse.json({ error: '缺少必填字段或无效的 ID' }, { status: 400 });
    }

    // Check ownership or admin role
    const existingChannel = await prisma.channel.findUnique({ where: { id: id } });
    if (!existingChannel) {
      return NextResponse.json({ error: '渠道未找到' }, { status: 404 });
    }
    if (userRole !== 'ADMIN' && existingChannel.userId !== userId) {
      return NextResponse.json({ error: '无权更新此渠道' }, { status: 403 });
    }

    const body = await request.json();
    const { name, providerId, modelIds, newUserId } = body; // Added newUserId

    if (isNaN(id) || !name || !providerId) {
      return NextResponse.json({ error: '缺少必填字段或无效的 ID' }, { status: 400 });
    }

    // Verify that the providerId exists
    const provider = await prisma.provider.findUnique({
      where: { id: providerId },
    });

    if (!provider) {
      return NextResponse.json({ error: '无效的提供商 ID' }, { status: 400 });
    }

    // Validate newUserId if provided and user is admin
    if (newUserId !== undefined && userRole !== 'ADMIN') {
      return NextResponse.json({ error: '无权更改渠道所有者' }, { status: 403 });
    }
    if (newUserId !== undefined) {
      const targetUser = await prisma.user.findUnique({ where: { id: newUserId } });
      if (!targetUser) {
        return NextResponse.json({ error: '目标用户不存在' }, { status: 400 });
      }
    }

    // Disconnect existing model routes not in the new list
    await prisma.modelRoute.deleteMany({
      where: {
        channelId: id,
        modelId: { notIn: modelIds || [] },
      },
    });

    // Connect new model routes
    const existingModelRoutes = await prisma.modelRoute.findMany({
      where: { channelId: id },
      select: { modelId: true },
    });
    const existingModelIds = existingModelRoutes.map(mr => mr.modelId);
    const modelsToConnect = (modelIds || []).filter((modelId: number) => !existingModelIds.includes(modelId));

    const updateData: any = {
      name,
      provider: {
        connect: { id: providerId },
      },
      modelRoutes: {
        create: modelsToConnect.map((modelId: number) => ({ model: { connect: { id: modelId } } })),
      },
    };

    if (newUserId !== undefined) {
      updateData.user = { connect: { id: newUserId } };
    }

    const updatedChannel = await prisma.channel.update({
      where: { id: id },
      data: updateData,
    });

    return NextResponse.json(updatedChannel);
  } catch (error) {
    console.error("Error updating channel:", error);
    if (error instanceof Error && 'code' in error && (error as { code: string }).code === 'P2002') {
      return NextResponse.json({ error: '此名称的渠道已存在' }, { status: 409 });
    }
    return NextResponse.json({ error: '更新渠道失败' }, { status: 500 });
  }
}

// DELETE /api/channels/[id] - Deletes a channel
export async function DELETE(request: AuthenticatedRequest, context: { params: Promise<{ id: string }> }) {
  try {
    const params = await context.params;
    const id = parseInt(params.id);
    const userId = request.user?.userId;
    const userRole = request.user?.role;

    if (isNaN(id)) {
      return NextResponse.json({ error: '缺少渠道 ID 或无效的 ID' }, { status: 400 });
    }

    // Check ownership or admin role
    const existingChannel = await prisma.channel.findUnique({ where: { id: id } });
    if (!existingChannel) {
      return NextResponse.json({ error: '渠道未找到' }, { status: 404 });
    }
    if (userRole !== 'ADMIN' && existingChannel.userId !== userId) {
      return NextResponse.json({ error: '无权删除此渠道' }, { status: 403 });
    }

    await prisma.channel.delete({
      where: { id: id },
    });

    return NextResponse.json({ message: '渠道删除成功' });
  } catch (error) {
    console.error("Error deleting channel:", error);
    return NextResponse.json({ error: '删除渠道失败' }, { status: 500 });
  }
}
