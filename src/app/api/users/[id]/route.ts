import { NextResponse } from 'next/server';
import { PrismaClient } from '@prisma/client';
import bcrypt from 'bcryptjs';
import { authMiddleware, AuthenticatedRequest } from '@/lib/auth';

const prisma = new PrismaClient();

// GET /api/users/[id] - 获取单个用户信息
export const GET = authMiddleware(async (request: AuthenticatedRequest, context: { params: Promise<{ id: string }> }) => {
  try {
    // 只有管理员可以获取用户信息
    if (request.user?.role !== 'ADMIN') {
      return NextResponse.json({ error: '未授权: 只有管理员可以访问' }, { status: 403 });
    }

    const params = await context.params;
    const { id } = params;
    const userId = parseInt(id, 10);

    if (isNaN(userId)) {
      return NextResponse.json({ error: '无效的用户 ID' }, { status: 400 });
    }

    const user = await prisma.user.findUnique({
      where: { id: userId },
      select: {
        id: true,
        email: true,
        role: true,
        disabled: true,
        validUntil: true,
        createdAt: true,
      },
    });

    if (!user) {
      return NextResponse.json({ error: '用户未找到' }, { status: 404 });
    }

    return NextResponse.json(user, { status: 200 });
  } catch (error) {
    console.error("获取用户信息错误:", error);
    return NextResponse.json({ error: '获取用户信息失败' }, { status: 500 });
  }
}, ['ADMIN']);

// PUT /api/users/[id] - 更新用户信息
export const PUT = authMiddleware(async (request: AuthenticatedRequest, context: { params: Promise<{ id: string }> }) => {
  try {
    // 只有管理员可以更新用户信息
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
    });

    if (!existingUser) {
      return NextResponse.json({ error: '用户未找到' }, { status: 404 });
    }

    const body = await request.json();
    const { email, password, role, disabled, validUntil } = body;

    // 准备更新数据
    const updateData: any = {
      role,
      disabled,
      validUntil: validUntil ? new Date(validUntil) : null,
    };

    // 如果提供了新邮箱且与当前邮箱不同，检查是否已存在
    if (email && email !== existingUser.email) {
      const emailUser = await prisma.user.findUnique({
        where: { email },
      });

      if (emailUser) {
        return NextResponse.json({ error: '邮箱已被其他用户使用' }, { status: 409 });
      }
      updateData.email = email;
    }

    // 如果提供了新密码，加密后更新
    if (password) {
      updateData.password = await bcrypt.hash(password, 10);
    }

    // 更新用户
    const user = await prisma.user.update({
      where: { id: userId },
      data: updateData,
      select: {
        id: true,
        email: true,
        role: true,
        disabled: true,
        validUntil: true,
        createdAt: true,
      },
    });

    return NextResponse.json(user, { status: 200 });
  } catch (error) {
    console.error("更新用户信息错误:", error);
    return NextResponse.json({ error: '更新用户信息失败' }, { status: 500 });
  }
}, ['ADMIN']);

// DELETE /api/users/[id] - 删除用户
export const DELETE = authMiddleware(async (request: AuthenticatedRequest, context: { params: Promise<{ id: string }> }) => {
  try {
    // 只有管理员可以删除用户
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
    });

    if (!existingUser) {
      return NextResponse.json({ error: '用户未找到' }, { status: 404 });
    }

    // 删除用户
    await prisma.user.delete({
      where: { id: userId },
    });

    return NextResponse.json({ message: '用户已删除' }, { status: 200 });
  } catch (error) {
    console.error("删除用户错误:", error);
    return NextResponse.json({ error: '删除用户失败' }, { status: 500 });
  }
}, ['ADMIN']);