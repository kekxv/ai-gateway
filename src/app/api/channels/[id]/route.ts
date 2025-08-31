import {NextResponse} from 'next/server';
import {authMiddleware, AuthenticatedRequest} from '@/lib/auth'; // Import authMiddleware
import {getInitializedDb} from '@/lib/db';

export const GET = authMiddleware(async (request: AuthenticatedRequest, context: {
  params: Promise<{ id: string }>
}) => {
  try {
    const params = await context.params;
    const {id} = params;
    const userId = request.user?.userId;
    const userRole = request.user?.role;

    const db = await getInitializedDb();

    let channel;
    if (userRole === 'ADMIN') {
      channel = await db.get('SELECT * FROM Channel WHERE id = ?', id);
    } else {
      channel = await db.get('SELECT * FROM Channel WHERE id = ? AND userId = ?', id, userId);
    }

    if (!channel) {
      return NextResponse.json({error: '渠道未找到或无权访问'}, {status: 404});
    }

    const channelProviders = await db.all(
      'SELECT providerId FROM ChannelProvider WHERE channelId = ?',
      channel.id
    );
    const providerIds = channelProviders.map((cp: any) => cp.providerId);

    if (providerIds.length > 0) {
      const providers = await db.all(
        `SELECT *
         FROM Provider
         WHERE id IN (${providerIds.map(() => '?').join(',')})`,
        ...providerIds
      );
      channel.providers = providers; // Attach an array of providers
    } else {
      channel.providers = [];
    }
    const rawModelRoutes = await db.all(
      `SELECT mr.*, m.name as model_name, m.description as model_description
       FROM ModelRoute mr
              JOIN Model m ON mr.modelId = m.id
       WHERE mr.channelId = ?`,
      channel.id
    );
    channel.modelRoutes = rawModelRoutes.map((mr: any) => ({
      ...mr,
      model: {
        id: mr.modelId,
        name: mr.model_name,
        description: mr.model_description,
      },
    }));

    return NextResponse.json(channel);
  } catch (error) {
    console.error("Error fetching channel:", error);
    return NextResponse.json({error: '获取渠道失败'}, {status: 500});
  }
});

export const PUT = authMiddleware(async (request: AuthenticatedRequest, context: {
  params: Promise<{ id: string }>
}) => {
  try {
    const params = await context.params;
    const {id} = params;
    const userId = request.user?.userId;
    const userRole = request.user?.role;

    const body = await request.json();
    const {name, providerIds, modelIds} = body; // Correctly destructure providerIds


    if (!name || !providerIds || providerIds.length === 0) { // This is the correct validation
      console.error('Validation failed: name, providerIds, or providerIds.length is invalid.');
      return NextResponse.json({error: '缺少必填字段或未选择提供商'}, {status: 400});
    }

    const db = await getInitializedDb(); // <-- Re-introducing this line

    // Check if channel exists and user has permission
    let existingChannel;
    if (userRole === 'ADMIN') {
      existingChannel = await db.get('SELECT * FROM Channel WHERE id = ?', id);
    } else {
      existingChannel = await db.get('SELECT * FROM Channel WHERE id = ? AND userId = ?', id, userId);
    }

    if (!existingChannel) {
      return NextResponse.json({error: '渠道未找到或无权修改'}, {status: 404});
    }

    // Validate providerIds
    for (const pId of providerIds) {
      const providerExists = await db.get('SELECT 1 FROM Provider WHERE id = ?', pId);
      if (!providerExists) {
        return NextResponse.json({error: `无效的提供商 ID: ${pId}`}, {status: 400});
      }
    }

    await db.run(
      'UPDATE Channel SET name = ?, updatedAt = CURRENT_TIMESTAMP WHERE id = ?',
      name,
      id
    );

    // Update ChannelProvider join table
    await db.run('DELETE FROM ChannelProvider WHERE channelId = ?', id);
    for (const pId of providerIds) {
      await db.run(
        'INSERT INTO ChannelProvider (channelId, providerId) VALUES (?, ?)',
        id,
        pId
      );
    }

    // Update ModelRoutes: first delete existing, then insert new ones
    await db.run('DELETE FROM ModelRoute WHERE channelId = ?', id);
    if (modelIds && modelIds.length > 0) {
      for (const modelId of modelIds) {
        await db.run(
          'INSERT INTO ModelRoute (modelId, channelId) VALUES (?, ?)',
          modelId,
          id
        );
      }
    }

    const updatedChannel = await db.get('SELECT * FROM Channel WHERE id = ?', id);

    return NextResponse.json(updatedChannel);
  } catch (error) {
    console.error("Error updating channel:", error);
    if (error instanceof Error && 'code' in error && (error as { code: string }).code === 'P2002') {
      return NextResponse.json({error: '此名称的渠道已存在'}, {status: 409});
    }
    return NextResponse.json({error: '更新渠道失败'}, {status: 500});
  }
});

export const DELETE = authMiddleware(async (request: AuthenticatedRequest, context: {
  params: Promise<{ id: string }>
}) => {
  try {
    const {id} = await context.params;
    const userId = request.user?.userId;
    const userRole = request.user?.role;

    const db = await getInitializedDb();

    // Check if channel exists and user has permission
    let existingChannel;
    if (userRole === 'ADMIN') {
      existingChannel = await db.get('SELECT * FROM Channel WHERE id = ?', id);
    } else {
      existingChannel = await db.get('SELECT * FROM Channel WHERE id = ? AND userId = ?', id, userId);
    }

    if (!existingChannel) {
      return NextResponse.json({error: '渠道未找到或无权删除'}, {status: 404});
    }

    // Delete associated ModelRoutes first
    await db.run('DELETE FROM ModelRoute WHERE channelId = ?', id);

    // Delete channel
    await db.run('DELETE FROM Channel WHERE id = ?', id);

    return NextResponse.json({message: '渠道删除成功'});
  } catch (error) {
    console.error("Error deleting channel:", error);
    return NextResponse.json({error: '删除渠道失败'}, {status: 500});
  }
});
