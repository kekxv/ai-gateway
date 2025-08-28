import { NextResponse } from 'next/server';
import { authMiddleware, AuthenticatedRequest } from '@/lib/auth';
import { PrismaClient } from '@prisma/client';
import { authenticator } from 'otplib';

const prisma = new PrismaClient();

async function verifyTotp(req: AuthenticatedRequest) {
  try {
    const userId = req.user?.userId;
    if (!userId) {
      return NextResponse.json({ error: '令牌中未找到用户' }, { status: 400 });
    }

    const { token } = await req.json();
    if (!token) {
      return NextResponse.json({ error: '必须提供令牌' }, { status: 400 });
    }

    const user = await prisma.user.findUnique({
      where: { id: userId },
    });

    if (!user || !user.totpSecret) {
      return NextResponse.json({ error: '该用户尚未设置TOTP' }, { status: 400 });
    }

    if (user.totpEnabled) {
      return NextResponse.json({ error: 'TOTP已被启用' }, { status: 400 });
    }

    const isValid = authenticator.check(token, user.totpSecret);

    if (!isValid) {
      return NextResponse.json({ error: '无效的TOTP令牌' }, { status: 400 });
    }

    await prisma.user.update({
      where: { id: userId },
      data: { totpEnabled: true },
    });

    return NextResponse.json({ message: 'TOTP已成功启用' });
  } catch (error) {
    console.error('验证TOTP失败:', error);
    return NextResponse.json({ error: '服务器内部错误' }, { status: 500 });
  }
}

export const POST = authMiddleware(verifyTotp);
