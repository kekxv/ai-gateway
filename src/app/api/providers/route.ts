import { NextResponse } from 'next/server';
import { PrismaClient } from '@prisma/client';
import { authMiddleware, AuthenticatedRequest } from '@/lib/auth'; // Import authMiddleware

const prisma = new PrismaClient();

// GET /api/providers - Fetches all providers
export const GET = authMiddleware(async (request: AuthenticatedRequest) => {
  try {
    const userId = request.user?.userId;
    const userRole = request.user?.role;

    let whereClause = {};
    if (userRole !== 'ADMIN') {
      whereClause = { userId: userId };
    }

    const providers = await prisma.provider.findMany({
      where: whereClause,
      include: {
        user: true, // Include the related user data
      },
      orderBy: {
        createdAt: 'desc',
      },
    });
    return NextResponse.json(providers, {
      headers: {
        'Cache-Control': 'no-store, no-cache, must-revalidate, proxy-revalidate',
        'Pragma': 'no-cache',
        'Expires': '0',
      },
    });
  } catch (error) {
    console.error("Error fetching providers:", error);
    return NextResponse.json({ error: '获取提供商失败' }, { status: 500 });
  }
});

// POST /api/providers - Creates a new provider
export const POST = authMiddleware(async (request: AuthenticatedRequest) => {
  try {
    const userId = request.user?.userId; // Get userId from authenticated request
    if (!userId) {
      return NextResponse.json({ error: '未授权: 用户ID缺失' }, { status: 401 });
    }

    const body = await request.json();
    const { name, baseURL, apiKey, type } = body;

    if (!name || !baseURL) { // apiKey is now optional
      return NextResponse.json({ error: '缺少必填字段' }, { status: 400 });
    }

    const newProvider = await prisma.provider.create({
      data: {
        name,
        baseURL,
        apiKey,
        type, // Add type here
        user: {
          connect: { id: userId }, // Assign userId via relation
        },
      },
    });

    return NextResponse.json(newProvider, { status: 201 });
  } catch (error) {
    console.error("Error creating provider:", error);
    if (error instanceof Error && 'code' in error && (error as { code: string }).code === 'P2002') {
      return NextResponse.json({ error: '此名称的提供商已存在' }, { status: 409 });
    }
    return NextResponse.json({ error: '创建提供商失败' }, { status: 500 });
  }
});
