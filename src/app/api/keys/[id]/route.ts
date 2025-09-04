import {NextResponse} from 'next/server';
import {authMiddleware, AuthenticatedRequest} from '@/lib/auth'; // Import authMiddleware
import {getInitializedDb} from '@/lib/db';

// PUT /api/keys/[id] - Updates an API key
export const PUT = authMiddleware(async (request: AuthenticatedRequest, context: { params: Promise<{ id: string }> }) => {
  try {
    const {id} = await context.params;
    const userId = request.user?.userId;
    const userRole = request.user?.role;

    if (isNaN(parseInt(id))) {
      return NextResponse.json({error: '缺少必填字段或无效的 ID'}, {status: 400});
    }

    // Check ownership or admin role
    const db = await getInitializedDb();
    const existingApiKey = await db.get('SELECT * FROM GatewayApiKey WHERE id = ?', id);
    if (!existingApiKey) {
      return NextResponse.json({error: 'API 密钥未找到'}, {status: 404});
    }
    if (userRole !== 'ADMIN' && existingApiKey.userId !== userId) {
      return NextResponse.json({error: '无权更新此 API 密钥'}, {status: 403});
    }

    const body = await request.json();
    const {name, enabled, newUserId, bindToAllChannels, channelIds, logDetails} = body; // Added logDetails

    if (!name) {
      return NextResponse.json({error: '缺少必填字段: 名称'}, {status: 400});
    }

    // Validate newUserId if provided and user is admin
    if (newUserId !== undefined && userRole !== 'ADMIN') {
      return NextResponse.json({error: '无权更改 API 密钥所有者'}, {status: 403});
    }
    if (newUserId !== undefined) {
      const targetUser = await db.get('SELECT * FROM User WHERE id = ?', newUserId);
      if (!targetUser) {
        return NextResponse.json({error: '目标用户不存在'}, {status: 400});
      }
    }

    const updateFields: string[] = [`name = ?`, `enabled = ?`, `bindToAllChannels = ?`, `logDetails = ?`]; // Added logDetails
    const updateValues: any[] = [name, enabled, bindToAllChannels || false, logDetails]; // Added logDetails

    if (newUserId !== undefined) {
      updateFields.push(`userId = ?`);
      updateValues.push(newUserId);
    }

    await db.run(
      `UPDATE GatewayApiKey
       SET ${updateFields.join(', ')}
       WHERE id = ?`,
      ...updateValues,
      id
    );

    // Update GatewayApiKeyChannel associations
    await db.run('DELETE FROM GatewayApiKeyChannel WHERE apiKeyId = ?', id); // Clear existing associations

    if (!bindToAllChannels && channelIds && channelIds.length > 0) {
      for (const channelId of channelIds) {
        // Optional: Validate channelId exists
        const channelExists = await db.get('SELECT 1 FROM Channel WHERE id = ?', channelId);
        if (!channelExists) {
          console.warn(`Channel ID ${channelId} not found for API key ${id}. Skipping association.`);
          continue;
        }
        await db.run(
          'INSERT INTO GatewayApiKeyChannel (apiKeyId, channelId) VALUES (?, ?)',
          id,
          channelId
        );
      }
    }

    // Fetch the updated API key
    const updatedApiKey = await db.get(`
      SELECT 
        gak.*, 
        u.email as userEmail,
        CASE 
          WHEN gak.bindToAllChannels = 1 THEN 'all'
          ELSE GROUP_CONCAT(c.id || ':' || c.name)
        END as channelsInfo
      FROM GatewayApiKey gak
      LEFT JOIN User u ON gak.userId = u.id
      LEFT JOIN GatewayApiKeyChannel gakc ON gak.id = gakc.apiKeyId
      LEFT JOIN Channel c ON gakc.channelId = c.id
      WHERE gak.id = ?
      GROUP BY gak.id
    `, id);

    return NextResponse.json(updatedApiKey);
  } catch (error) {
    console.error("Error updating API key:", error);
    return NextResponse.json({error: '更新 API 密钥失败'}, {status: 500});
  }
});

// DELETE /api/keys/[id] - Disables an API key instead of deleting it
export const DELETE = authMiddleware(async (request: AuthenticatedRequest, context: { params: Promise<{ id: string }> }) => {
  try {
    const {id} = await context.params;
    const userId = request.user?.userId;
    const userRole = request.user?.role;

    if (isNaN(parseInt(id))) {
      return NextResponse.json({error: '缺少 API 密钥 ID 或无效的 ID'}, {status: 400});
    }

    // Check ownership or admin role
    const db = await getInitializedDb();
    const existingApiKey = await db.get('SELECT * FROM GatewayApiKey WHERE id = ?', id);
    if (!existingApiKey) {
      return NextResponse.json({error: 'API 密钥未找到'}, {status: 404});
    }
    if (userRole !== 'ADMIN' && existingApiKey.userId !== userId) {
      return NextResponse.json({error: '无权禁用此 API 密钥'}, {status: 403});
    }

    // Disable the API key instead of deleting it
    await db.run('UPDATE GatewayApiKey SET enabled = FALSE WHERE id = ?', id);

    return NextResponse.json({message: 'API 密钥已禁用'});
  } catch (error) {
    console.error("Error disabling API key:", error);
    return NextResponse.json({error: '禁用 API 密钥失败'}, {status: 500});
  }
});
