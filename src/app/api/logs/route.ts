import { NextResponse } from 'next/server';
import { PrismaClient } from '@prisma/client';
import { authMiddleware, AuthenticatedRequest } from '@/lib/auth'; // Import authMiddleware

const prisma = new PrismaClient();

export const GET = authMiddleware(async (request: AuthenticatedRequest) => {
  const { searchParams } = new URL(request.url);
  const page = parseInt(searchParams.get('page') || '1', 10);
  const limit = parseInt(searchParams.get('limit') || '10', 10);
  const skip = (page - 1) * limit;

  try {
    const userId = request.user?.userId;
    const userRole = request.user?.role;

    let whereClause: any = {};
    if (userRole !== 'ADMIN') {
      whereClause = {
        apiKey: {
          userId: userId,
        },
      };
    }

    const logs = await prisma.log.findMany({
      where: whereClause,
      skip,
      take: limit,
      orderBy: {
        createdAt: 'desc',
      },
      select: {
        id: true,
        createdAt: true,
        latency: true,
        promptTokens: true,
        completionTokens: true,
        totalTokens: true,
        requestBody: true,
        responseBody: true,
        apiKey: {
          select: {
            name: true,
            user: {
              select: {
                email: true,
                role: true,
              },
            },
          },
        },
        modelRoute: {
          include: {
            model: {
              select: {
                name: true,
              },
            },
            channel: {
              select: {
                name: true,
              },
            },
          },
        },
      },
    });

    const totalLogs = await prisma.log.count({ where: whereClause }); // Apply filtering to count as well
    console.log(`Total logs: ${totalLogs}, Limit: ${limit}`); // Add console.log

    return NextResponse.json({
      logs,
      totalPages: Math.ceil(totalLogs / limit),
      currentPage: page,
    }, {
      headers: {
        'Cache-Control': 'no-store, no-cache, must-revalidate, proxy-revalidate',
        'Pragma': 'no-cache',
        'Expires': '0',
      },
    });
  } catch (error) {
    console.error("Error fetching logs:", error);
    return NextResponse.json({ error: 'An internal server error occurred.' }, { status: 500 });
  }
});