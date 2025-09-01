import { NextResponse } from 'next/server';
import { authMiddleware, AuthenticatedRequest } from '@/lib/auth'; // Import authMiddleware
import { getInitializedDb } from '@/lib/db';

// GET /api/keys - Fetches all API keys
export const GET = authMiddleware(async (request: AuthenticatedRequest) => {
  try {
    const userId = request.user?.userId;
    const userRole = request.user?.role;

    const db = await getInitializedDb();

    const apiKeys = await db.all(
      `SELECT * FROM GatewayApiKey ${userRole !== 'ADMIN' ? 'WHERE userId = ?' : ''} ORDER BY createdAt DESC`,
      ...(userRole !== 'ADMIN' ? [userId] : [])
    );

    for (const apiKey of apiKeys) {
      if (apiKey.userId) {
        apiKey.user = await db.get('SELECT id, email, role FROM User WHERE id = ?', apiKey.userId);
      }
      // Fetch associated channels if not bound to all channels
      if (!apiKey.bindToAllChannels) {
        const associatedChannels = await db.all(
          `SELECT gac.channelId, c.name
           FROM GatewayApiKeyChannel gac
           JOIN Channel c ON gac.channelId = c.id
           WHERE gac.apiKeyId = ?`,
          apiKey.id
        );
        apiKey.channels = associatedChannels.map((ac: any) => ({ id: ac.channelId, name: ac.name }));
      } else {
        apiKey.channels = []; // Or a special flag indicating all channels
      }
    }
    return NextResponse.json(apiKeys, {
      headers: {
        'Cache-Control': 'no-store, no-cache, must-revalidate, proxy-revalidate',
        'Pragma': 'no-cache',
        'Expires': '0',
      },
    });
  } catch (error) {
    console.error("Error fetching API keys:", error);
    return NextResponse.json({ error: '获取 API 密钥失败' }, { status: 500 });
  }
});

import { v4 as uuidv4 } from 'uuid';

// POST /api/keys - Creates a new API key
export const POST = authMiddleware(async (request: AuthenticatedRequest) => {
  try {
    const userId = request.user?.userId; // Get userId from authenticated request
    if (!userId) {
      return NextResponse.json({ error: '未授权: 用户ID缺失' }, { status: 401 });
    }

    const body = await request.json();
    const { name, bindToAllChannels, channelIds } = body; // Added bindToAllChannels and channelIds

    if (!name) {
      return NextResponse.json({ error: '缺少必填字段: 名称' }, { status: 400 });
    }

    const db = await getInitializedDb();
    const newKey = uuidv4(); // Generate a new UUID for the key
    const result = await db.run(
      'INSERT INTO GatewayApiKey (name, userId, key, bindToAllChannels) VALUES (?, ?, ?, ?)', // Added bindToAllChannels
      name,
      userId,
      newKey,
      bindToAllChannels || false // Default to false if not provided
    );
    const newApiKeyId = result.lastID;

    // If not binding to all channels, associate with specific channels
    if (!bindToAllChannels && channelIds && channelIds.length > 0) {
      for (const channelId of channelIds) {
        // Optional: Validate channelId exists
        const channelExists = await db.get('SELECT 1 FROM Channel WHERE id = ?', channelId);
        if (!channelExists) {
          console.warn(`Channel ID ${channelId} not found for API key ${newApiKeyId}. Skipping association.`);
          continue;
        }
        await db.run(
          'INSERT INTO GatewayApiKeyChannel (apiKeyId, channelId) VALUES (?, ?)',
          newApiKeyId,
          channelId
        );
      }
    }

    const newApiKey = await db.get('SELECT * FROM GatewayApiKey WHERE id = ?', newApiKeyId);

    return NextResponse.json(newApiKey, { status: 201 });
  } catch (error) {
    console.error("Error creating API key:", error);
    return NextResponse.json({ error: '创建 API 密钥失败' }, { status: 500 });
  }
});
