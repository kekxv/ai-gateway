import { NextResponse } from 'next/server';
import { authMiddleware, AuthenticatedRequest } from '@/lib/auth'; // Import authMiddleware
import { getInitializedDb } from '@/lib/db';

const handleGet = authMiddleware(async (request: AuthenticatedRequest) => {
  try {
    const userId = request.user?.userId;
    const userRole = request.user?.role;

    let whereClause = {};
    if (userRole !== 'ADMIN') {
      whereClause = { userId: userId };
    }

    const db = await getInitializedDb();

    const channels = await db.all(
      `SELECT * FROM Channel ${userRole !== 'ADMIN' ? 'WHERE userId = ?' : ''} ORDER BY createdAt DESC`,
      ...(userRole !== 'ADMIN' ? [userId] : [])
    );

    for (const channel of channels) {
      channel.provider = await db.get('SELECT * FROM Provider WHERE id = ?', channel.providerId);
      const rawModelRoutes = await db.all(
        `SELECT mr.*, m.name as model_name, m.description as model_description
         FROM ModelRoute mr
         JOIN Model m ON mr.modelId = m.id
         WHERE mr.channelId = ?`,
        channel.id
      );
      // 重新封装 model_name 和 model_description 到 model 对象中
      channel.modelRoutes = rawModelRoutes.map((mr: any) => ({
        ...mr,
        model: {
          name: mr.model_name,
          description: mr.model_description,
        },
      }));
    }
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
});

const handlePost = authMiddleware(async (request: AuthenticatedRequest) => {
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

    const db = await getInitializedDb();
    const provider = await db.get('SELECT * FROM Provider WHERE id = ?', providerId);

    if (!provider) {
      return NextResponse.json({ error: '无效的提供商 ID' }, { status: 400 });
    }

    const result = await db.run(
      'INSERT INTO Channel (name, userId, providerId) VALUES (?, ?, ?)',
      name,
      userId,
      providerId
    );
    const newChannelId = result.lastID;

    if (modelIds && modelIds.length > 0) {
      for (const modelId of modelIds) {
        await db.run(
          'INSERT INTO ModelRoute (modelId, channelId) VALUES (?, ?)',
          modelId,
          newChannelId
        );
      }
    }

    const newChannel = await db.get('SELECT * FROM Channel WHERE id = ?', newChannelId);

    return NextResponse.json(newChannel, { status: 201 });
  } catch (error) {
    console.error("Error creating channel:", error);
    // Prisma unique constraint violation code
    if (error instanceof Error && 'code' in error && (error as { code: string }).code === 'P2002') {
         return NextResponse.json({ error: '此名称的渠道已存在' }, { status: 409 });
    }
    return NextResponse.json({ error: '创建渠道失败' }, { status: 500 });
  }
});

export { handleGet as GET, handlePost as POST };