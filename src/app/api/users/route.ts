import { NextResponse } from 'next/server';
import { PrismaClient } from '@prisma/client';
import bcrypt from 'bcryptjs';
import { authMiddleware, AuthenticatedRequest } from '@/lib/auth';

const prisma = new PrismaClient();

// GET /api/users - 获取用户列表
export const GET = authMiddleware(async (request: AuthenticatedRequest) => {
  try {
    // 只有管理员可以获取用户列表
    if (request.user?.role !== 'ADMIN') {
      return NextResponse.json({ error: '未授权: 只有管理员可以访问' }, { status: 403 });
    }

    const users = await prisma.user.findMany({
      select: {
        id: true,
        email: true,
        role: true,
        disabled: true,
        validUntil: true,
        createdAt: true,
      },
      orderBy: {
        createdAt: 'desc',
      },
    });

    return NextResponse.json(users, { status: 200 });
  } catch (error) {
    console.error("获取用户列表错误:", error);
    return NextResponse.json({ error: '获取用户列表失败' }, { status: 500 });
  }
}, ['ADMIN']);

// POST /api/users - 创建新用户
export const POST = authMiddleware(async (request: AuthenticatedRequest) => {
  try {
    // 只有管理员可以创建用户
    if (request.user?.role !== 'ADMIN') {
      return NextResponse.json({ error: '未授权: 只有管理员可以访问' }, { status: 403 });
    }

    const body = await request.json();
    const { email, password, role, disabled, validUntil } = body;

    // 验证必填字段
    if (!email || !password) {
      return NextResponse.json({ error: '邮箱和密码是必填项' }, { status: 400 });
    }

    // 检查用户是否已存在
    const existingUser = await prisma.user.findUnique({
      where: { email },
    });

    if (existingUser) {
      return NextResponse.json({ error: '用户已存在' }, { status: 409 });
    }

    // 加密密码
    const hashedPassword = await bcrypt.hash(password, 10);

    // 创建用户
    const user = await prisma.user.create({
      data: {
        email,
        password: hashedPassword,
        role: role || 'USER',
        disabled: disabled || false,
        validUntil: validUntil ? new Date(validUntil) : null,
      },
      select: {
        id: true,
        email: true,
        role: true,
        disabled: true,
        validUntil: true,
        createdAt: true,
      },
    });

    return NextResponse.json(user, { status: 201 });
  } catch (error) {
    console.error("创建用户错误:", error);
    return NextResponse.json({ error: '创建用户失败' }, { status: 500 });
  }
}, ['ADMIN']);