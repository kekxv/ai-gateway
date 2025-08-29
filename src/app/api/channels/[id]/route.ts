import { NextResponse } from 'next/server';
import { AuthenticatedRequest } from '@/lib/auth'; // Import authMiddleware
import { getInitializedDb } from '@/lib/db';

export async function GET(request: AuthenticatedRequest, context: { params: Promise<{ id: string }> }) {
  try {
    const params = await context.params;
    const id = parseInt(params.id);
    const userId = request.user?.userId;
    const userRole = request.user?.role;

    if (isNaN(id)) {
      return NextResponse.json({ error: '无效的 ID' }, { status: 400 });
    }

    let whereClause: any = { id: id };
    if (userRole !== 'ADMIN') {
      whereClause = { ...whereClause, userId: userId };
    }

    const db = await getInitializedDb();

    const channel = await db.get(
      `SELECT * FROM Channel WHERE id = ? ${userRole !== 'ADMIN' ? 'AND userId = ?' : ''}`,
      id,
      ...(userRole !== 'ADMIN' ? [userId] : [])
    );

    if (channel) {
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

    if (!channel) {
      return NextResponse.json({ error: '渠道未找到或无权访问' }, { status: 404 });
    }

    return NextResponse.json(channel);
  } catch (error) {
    console.error("Error fetching channel:", error);
    return NextResponse.json({ error: '获取渠道失败' }, { status: 500 });
  }
}

// PUT /api/channels/[id] - Updates a channel
export async function PUT(request: AuthenticatedRequest, context: { params: Promise<{ id: string }> }) {
  try {
    const params = await context.params;
    const id = parseInt(params.id);
    const userId = request.user?.userId;
    const userRole = request.user?.role;

    if (isNaN(id)) {
      return NextResponse.json({ error: '缺少必填字段或无效的 ID' }, { status: 400 });
    }

    // Check ownership or admin role
    const db = await getInitializedDb();
    const existingChannel = await db.get('SELECT * FROM Channel WHERE id = ?', id);
    if (!existingChannel) {
      return NextResponse.json({ error: '渠道未找到' }, { status: 404 });
    }
    if (userRole !== 'ADMIN' && existingChannel.userId !== userId) {
      return NextResponse.json({ error: '无权更新此渠道' }, { status: 403 });
    }

    const body = await request.json();
    const { name, providerId, modelIds, newUserId } = body; // Added newUserId

    if (isNaN(id) || !name || !providerId) {
      return NextResponse.json({ error: '缺少必填字段或无效的 ID' }, { status: 400 });
    }

    // Verify that the providerId exists
    const provider = await db.get('SELECT * FROM Provider WHERE id = ?', providerId);

    if (!provider) {
      return NextResponse.json({ error: '无效的提供商 ID' }, { status: 400 });
    }

    // Validate newUserId if provided and user is admin
    if (newUserId !== undefined && userRole !== 'ADMIN') {
      return NextResponse.json({ error: '无权更改渠道所有者' }, { status: 403 });
    }
    if (newUserId !== undefined) {
      const targetUser = await db.get('SELECT * FROM User WHERE id = ?', newUserId);
      if (!targetUser) {
        return NextResponse.json({ error: '目标用户不存在' }, { status: 400 });
      }
    }

    if (modelIds && modelIds.length > 0) {
      await db.run(
        `DELETE FROM ModelRoute WHERE channelId = ? AND modelId NOT IN (${modelIds.map(() => '?').join(',')})`,
        id,
        ...modelIds
      );
    } else {
      // If modelIds is empty or null, delete all model routes for this channel
      await db.run('DELETE FROM ModelRoute WHERE channelId = ?', id);
    }

    // Connect new model routes
    const existingModelRoutes = await db.all(
      'SELECT modelId FROM ModelRoute WHERE channelId = ?',
      id
    );
    const existingModelIds = existingModelRoutes.map((mr: { modelId: number }) => mr.modelId);
    const modelsToConnect = (modelIds || []).filter((modelId: number) => !existingModelIds.includes(modelId));

    const updateFields: string[] = [`name = ?`, `providerId = ?`, `updatedAt = CURRENT_TIMESTAMP`];
    const updateValues: any[] = [name, providerId];

    if (newUserId !== undefined) {
      updateFields.push(`userId = ?`);
      updateValues.push(newUserId);
    }

    await db.run(
      `UPDATE Channel SET ${updateFields.join(', ')} WHERE id = ?`,
      ...updateValues,
      id
    );

    for (const modelId of modelsToConnect) {
      await db.run(
        'INSERT INTO ModelRoute (modelId, channelId) VALUES (?, ?)',
        modelId,
        id
      );
    }

    const updatedChannel = await db.get('SELECT * FROM Channel WHERE id = ?', id);

    return NextResponse.json(updatedChannel);
  } catch (error) {
    console.error("Error updating channel:", error);
    if (error instanceof Error && 'code' in error && (error as { code: string }).code === 'P2002') {
      return NextResponse.json({ error: '此名称的渠道已存在' }, { status: 409 });
    }
    return NextResponse.json({ error: '更新渠道失败' }, { status: 500 });
  }
}

// DELETE /api/channels/[id] - Deletes a channel
export async function DELETE(request: AuthenticatedRequest, context: { params: Promise<{ id: string }> }) {
  try {
    const params = await context.params;
    const id = parseInt(params.id);
    const userId = request.user?.userId;
    const userRole = request.user?.role;

    if (isNaN(id)) {
      return NextResponse.json({ error: '缺少渠道 ID 或无效的 ID' }, { status: 400 });
    }

    // Check ownership or admin role
    const db = await getInitializedDb();
    const existingChannel = await db.get('SELECT * FROM Channel WHERE id = ?', id);
    if (!existingChannel) {
      return NextResponse.json({ error: '渠道未找到' }, { status: 404 });
    }
    if (userRole !== 'ADMIN' && existingChannel.userId !== userId) {
      return NextResponse.json({ error: '无权删除此渠道' }, { status: 403 });
    }

    await db.run('DELETE FROM Channel WHERE id = ?', id);

    return NextResponse.json({ message: '渠道删除成功' });
  } catch (error) {
    console.error("Error deleting channel:", error);
    return NextResponse.json({ error: '删除渠道失败' }, { status: 500 });
  }
}
