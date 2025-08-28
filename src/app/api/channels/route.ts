import { NextResponse } from 'next/server';
import { PrismaClient } from '@prisma/client';
import { authMiddleware, AuthenticatedRequest } from '@/lib/auth'; // Import authMiddleware

const prisma = new PrismaClient();

// GET /api/channels - Fetches all channels
export async function GET(request: AuthenticatedRequest) {
  try {
    const userId = request.user?.userId;
    const userRole = request.user?.role;

    let whereClause = {};
    if (userRole !== 'ADMIN') {
      whereClause = { userId: userId };
    }

    const channels = await prisma.channel.findMany({
      where: whereClause,
      include: {
        provider: true, // Include the related provider data
        modelRoutes: {
          include: {
            model: true, // Include the related model data
          },
        },
      },
      orderBy: {
        createdAt: 'desc',
      },
    });
    return NextResponse.json(channels, {
      headers: {
        'Cache-Control': 'no-store, no-cache, must-revalidate, proxy-revalidate',
        'Pragma': 'no-cache',
        'Expires': '0',
      },
    });
  } catch (error) {
    console.error("Error fetching channels:", error);
    return NextResponse.json({ error: '获取渠道失败' }, { status: 500 });
  }
}

// POST /api/channels - Creates a new channel
export async function POST(request: AuthenticatedRequest) {
  try {
    const userId = request.user?.userId; // Get userId from authenticated request
    if (!userId) {
      return NextResponse.json({ error: '未授权: 用户ID缺失' }, { status: 401 });
    }

    const body = await request.json();
    const { name, providerId, modelIds } = body;

    if (!name || !providerId) {
      return NextResponse.json({ error: '缺少必填字段' }, { status: 400 });
    }

    const provider = await prisma.provider.findUnique({
      where: { id: providerId },
    });

    if (!provider) {
      return NextResponse.json({ error: '无效的提供商 ID' }, { status: 400 });
    }

    const newChannel = await prisma.channel.create({
      data: {
        name,
        user: {
          connect: { id: userId }, // Assign userId via relation
        },
        // Removed apiKey
        provider: {
          connect: { id: providerId },
        },
        modelRoutes: {
          create: modelIds ? modelIds.map((modelId: number) => ({ model: { connect: { id: modelId } } })) : [],
        },
      },
    });

    return NextResponse.json(newChannel, { status: 201 });
  } catch (error) {
    console.error("Error creating channel:", error);
    // Prisma unique constraint violation code
    if (error instanceof Error && 'code' in error && (error as { code: string }).code === 'P2002') {
         return NextResponse.json({ error: '此名称的渠道已存在' }, { status: 409 });
    }
    return NextResponse.json({ error: '创建渠道失败' }, { status: 500 });
  }
}
