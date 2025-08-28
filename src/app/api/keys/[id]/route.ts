import { NextResponse } from 'next/server';
import { PrismaClient } from '@prisma/client';
import { AuthenticatedRequest } from '@/lib/auth'; // Import authMiddleware

const prisma = new PrismaClient();

// PUT /api/keys/[id] - Updates an API key
export async function PUT(request: AuthenticatedRequest, context: { params: Promise<{ id: string }> }) {
  try {
    const params = await context.params;
    const id = parseInt(params.id); // Extract id from context.params
    const userId = request.user?.userId;
    const userRole = request.user?.role;

    if (isNaN(id)) {
      return NextResponse.json({ error: '缺少必填字段或无效的 ID' }, { status: 400 });
    }

    // Check ownership or admin role
    const existingApiKey = await prisma.gatewayApiKey.findUnique({ where: { id: id } });
    if (!existingApiKey) {
      return NextResponse.json({ error: 'API 密钥未找到' }, { status: 404 });
    }
    if (userRole !== 'ADMIN' && existingApiKey.userId !== userId) {
      return NextResponse.json({ error: '无权更新此 API 密钥' }, { status: 403 });
    }

    const body = await request.json();
    const { name, enabled, newUserId } = body; // Added newUserId

    if (!name) {
      return NextResponse.json({ error: '缺少必填字段: 名称' }, { status: 400 });
    }

    // Validate newUserId if provided and user is admin
    if (newUserId !== undefined && userRole !== 'ADMIN') {
      return NextResponse.json({ error: '无权更改 API 密钥所有者' }, { status: 403 });
    }
    if (newUserId !== undefined) {
      const targetUser = await prisma.user.findUnique({ where: { id: newUserId } });
      if (!targetUser) {
        return NextResponse.json({ error: '目标用户不存在' }, { status: 400 });
      }
    }

    const updateData: any = {
      name,
      enabled,
    };

    if (newUserId !== undefined) {
      updateData.user = { connect: { id: newUserId } };
    }

    const updatedApiKey = await prisma.gatewayApiKey.update({
      where: { id: id },
      data: updateData,
    });

    return NextResponse.json(updatedApiKey);
  } catch (error) {
    console.error("Error updating API key:", error);
    return NextResponse.json({ error: '更新 API 密钥失败' }, { status: 500 });
  }
}

// DELETE /api/keys/[id] - Deletes an API key
export async function DELETE(request: AuthenticatedRequest, context: { params: Promise<{ id: string }> }) {
  try {
    const params = await context.params;
    const id = parseInt(params.id);
    const userId = request.user?.userId;
    const userRole = request.user?.role;

    if (isNaN(id)) {
      return NextResponse.json({ error: '缺少 API 密钥 ID 或无效的 ID' }, { status: 400 });
    }

    // Check ownership or admin role
    const existingApiKey = await prisma.gatewayApiKey.findUnique({ where: { id: id } });
    if (!existingApiKey) {
      return NextResponse.json({ error: 'API 密钥未找到' }, { status: 404 });
    }
    if (userRole !== 'ADMIN' && existingApiKey.userId !== userId) {
      return NextResponse.json({ error: '无权删除此 API 密钥' }, { status: 403 });
    }

    await prisma.gatewayApiKey.delete({
      where: { id: id },
    });

    return NextResponse.json({ message: 'API 密钥删除成功' });
  } catch (error) {
    console.error("Error deleting API key:", error);
    return NextResponse.json({ error: '删除 API 密钥失败' }, { status: 500 });
  }
}