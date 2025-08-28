import { NextResponse } from 'next/server';
import { PrismaClient } from '@prisma/client';
import { authMiddleware, AuthenticatedRequest } from '@/lib/auth';

const prisma = new PrismaClient();

// POST /api/users/[id]/toggle-disabled - 切换用户禁用状态
export const POST = authMiddleware(async (request: AuthenticatedRequest, context: { params: Promise<{ id: string }> }) => {
  try {
    // 只有管理员可以切换用户禁用状态
    if (request.user?.role !== 'ADMIN') {
      return NextResponse.json({ error: '未授权: 只有管理员可以访问' }, { status: 403 });
    }

    const params = await context.params;
    const { id } = params;
    const userId = parseInt(id, 10);

    if (isNaN(userId)) {
      return NextResponse.json({ error: '无效的用户 ID' }, { status: 400 });
    }

    // 检查用户是否存在
    const existingUser = await prisma.user.findUnique({
      where: { id: userId },
      select: {
        id: true,
        disabled: true,
      },
    });

    if (!existingUser) {
      return NextResponse.json({ error: '用户未找到' }, { status: 404 });
    }

    // 切换禁用状态
    const updatedUser = await prisma.user.update({
      where: { id: userId },
      data: {
        disabled: !existingUser.disabled,
      },
      select: {
        id: true,
        email: true,
        disabled: true,
      },
    });

    const action = updatedUser.disabled ? '禁用' : '启用';
    return NextResponse.json({ 
      message: `用户已${action}`, 
      user: updatedUser 
    }, { status: 200 });
  } catch (error) {
    console.error("切换用户禁用状态错误:", error);
    return NextResponse.json({ error: '切换用户禁用状态失败' }, { status: 500 });
  }
}, ['ADMIN']);