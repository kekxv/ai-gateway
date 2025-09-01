import { NextResponse } from 'next/server';
import { authMiddleware, AuthenticatedRequest } from '@/lib/auth'; // Import authMiddleware
import { getInitializedDb } from '@/lib/db';

const handleGet = authMiddleware(async (request: AuthenticatedRequest) => {
  try {
    const userId = request.user?.userId;
    const userRole = request.user?.role;

    const db = await getInitializedDb();

    let channels;
    if (userRole === 'ADMIN') {
      // Admins see all channels
      channels = await db.all('SELECT * FROM Channel ORDER BY createdAt DESC');
    } else {
      // Regular users see their own channels and shared channels
      channels = await db.all(
        'SELECT * FROM Channel WHERE userId = ? OR shared = 1 ORDER BY createdAt DESC',
        userId
      );
    }

    for (const channel of channels) {
      const channelProviders = await db.all(
        'SELECT providerId FROM ChannelProvider WHERE channelId = ?',
        channel.id
      );
      const providerIds = channelProviders.map((cp: any) => cp.providerId);

      if (providerIds.length > 0) {
        const providers = await db.all(
          `SELECT * FROM Provider WHERE id IN (${providerIds.map(() => '?').join(',')})`,
          ...providerIds
        );
        channel.providers = providers;
      } else {
        channel.providers = [];
      }

      const allowedModels = await db.all(
        `SELECT m.id, m.name, m.alias
         FROM Model m
         JOIN ChannelAllowedModel cam ON m.id = cam.modelId
         WHERE cam.channelId = ?`,
        channel.id
      );
      channel.models = allowedModels;
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
    const userId = request.user?.userId;
    if (!userId) {
      return NextResponse.json({ error: '未授权: 用户ID缺失' }, { status: 401 });
    }

    const body = await request.json();
    const { name, providerIds, modelIds, shared } = body;

    if (!name || !providerIds || providerIds.length === 0) {
      return NextResponse.json({ error: '缺少必填字段或未选择提供商' }, { status: 400 });
    }

    const db = await getInitializedDb();

    for (const pId of providerIds) {
      const providerExists = await db.get('SELECT 1 FROM Provider WHERE id = ?', pId);
      if (!providerExists) {
        return NextResponse.json({ error: `无效的提供商 ID: ${pId}` }, { status: 400 });
      }
    }

    const result = await db.run(
      'INSERT INTO Channel (name, userId, shared) VALUES (?, ?, ?)',
      name,
      userId,
      shared || false
    );
    const newChannelId = result.lastID;

    for (const pId of providerIds) {
      await db.run(
        'INSERT INTO ChannelProvider (channelId, providerId) VALUES (?, ?)',
        newChannelId,
        pId
      );
    }

    if (modelIds && modelIds.length > 0) {
      for (const modelId of modelIds) {
        await db.run(
          'INSERT OR IGNORE INTO ChannelAllowedModel (channelId, modelId) VALUES (?, ?)',
          newChannelId,
          modelId
        );
      }
    }

    const newChannel = await db.get('SELECT * FROM Channel WHERE id = ?', newChannelId);

    return NextResponse.json(newChannel, { status: 201 });
  } catch (error) {
    console.error("Error creating channel:", error);
    if (error instanceof Error && 'code' in error && (error as { code: string }).code === 'P2002') {
         return NextResponse.json({ error: '此名称的渠道已存在' }, { status: 409 });
    }
    return NextResponse.json({ error: '创建渠道失败' }, { status: 500 });
  }
});

export { handleGet as GET, handlePost as POST };