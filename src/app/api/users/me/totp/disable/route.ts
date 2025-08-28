import { NextResponse } from 'next/server';
import { authMiddleware, AuthenticatedRequest } from '@/lib/auth';
import { PrismaClient } from '@prisma/client';
import bcrypt from 'bcryptjs';

const prisma = new PrismaClient();

async function disableTotp(req: AuthenticatedRequest) {
  try {
    const userId = req.user?.userId;
    if (!userId) {
      return NextResponse.json({ error: '令牌中未找到用户' }, { status: 400 });
    }

    const { password } = await req.json();
    if (!password) {
      return NextResponse.json({ error: '必须提供密码' }, { status: 400 });
    }

    const user = await prisma.user.findUnique({
      where: { id: userId },
    });

    if (!user) {
      return NextResponse.json({ error: '用户未找到' }, { status: 404 });
    }

    if (!user.totpEnabled) {
      return NextResponse.json({ error: '该用户尚未启用TOTP' }, { status: 400 });
    }

    const isPasswordValid = await bcrypt.compare(password, user.password);

    if (!isPasswordValid) {
      return NextResponse.json({ error: '密码无效' }, { status: 401 });
    }

    await prisma.user.update({
      where: { id: userId },
      data: {
        totpEnabled: false,
        totpSecret: null,
      },
    });

    return NextResponse.json({ message: 'TOTP已成功禁用' });
  } catch (error) {
    console.error('禁用TOTP失败:', error);
    return NextResponse.json({ error: '服务器内部错误' }, { status: 500 });
  }
}

export const POST = authMiddleware(disableTotp);
