import { NextResponse } from 'next/server';
import { authMiddleware, AuthenticatedRequest } from '@/lib/auth';
import { PrismaClient } from '@prisma/client';
import { authenticator } from 'otplib';
import qrcode from 'qrcode';

const prisma = new PrismaClient();
const SERVICE_NAME = 'AI Gateway';

async function setupTotp(req: AuthenticatedRequest) {
  try {
    const userId = req.user?.userId;
    const userEmail = req.user?.email;

    if (!userId || !userEmail) {
      return NextResponse.json({ error: '令牌中未找到用户' }, { status: 400 });
    }

    const user = await prisma.user.findUnique({ where: { id: userId } });
    if (!user) {
      return NextResponse.json({ error: '用户未找到' }, { status: 404 });
    }

    // 如果已启用TOTP，应先禁用它。
    if (user.totpEnabled) {
      return NextResponse.json({ error: 'TOTP 已启用。如需设置新密钥，请先禁用当前密钥。' }, { status: 400 });
    }

    const secret = authenticator.generateSecret();
    const otpauth = authenticator.keyuri(userEmail, SERVICE_NAME, secret);

    await prisma.user.update({
      where: { id: userId },
      data: {
        totpSecret: secret, // 在生产环境中，此密钥应加密存储
        totpEnabled: false, // 在验证前不启用
      },
    });

    const qrCodeDataUrl = await qrcode.toDataURL(otpauth);

    return NextResponse.json({
      secret, // 用于手动输入
      qrCodeDataUrl,
    });
  } catch (error) {
    console.error('设置TOTP失败:', error);
    return NextResponse.json({ error: '服务器内部错误' }, { status: 500 });
  }
}

export const POST = authMiddleware(setupTotp);
