import { NextResponse } from 'next/server';
import { getInitializedDb } from '@/lib/db';

export async function GET(request: Request) {
  try {
    // 1. Authenticate the request
    const authHeader = request.headers.get('Authorization');
    if (!authHeader || !authHeader.startsWith('Bearer ')) {
      return NextResponse.json({ error: 'Unauthorized: Missing or invalid Authorization header' }, { status: 401 });
    }
    const apiKey = authHeader.split(' ')[1];
    const db = await getInitializedDb();
    const dbKey = await db.get('SELECT * FROM GatewayApiKey WHERE key = ?', apiKey);

    if (!dbKey || !dbKey.enabled) {
      return NextResponse.json({ error: 'Unauthorized: Invalid API Key' }, { status: 401 });
    }

    // Non-blocking update of lastUsed time
    db.run('UPDATE GatewayApiKey SET lastUsed = ? WHERE id = ?', new Date().toISOString(), dbKey.id).catch(console.error);

    let models;
    if (dbKey.bindToAllChannels) {
      // If key can access all channels, return all models explicitly allowed in any channel
      models = await db.all(`
        SELECT DISTINCT m.*
        FROM Model m
        JOIN ChannelAllowedModel cam ON m.id = cam.modelId
      `);
    } else {
      // If key is bound to specific channels, return models allowed in those channels
      models = await db.all(`
        SELECT DISTINCT m.*
        FROM Model m
        WHERE m.id IN (
          SELECT cam.modelId
          FROM ChannelAllowedModel cam
          WHERE cam.channelId IN (
            SELECT gac.channelId
            FROM GatewayApiKeyChannel gac
            WHERE gac.apiKeyId = ?
          )
        )
      `, dbKey.id);
    }

    const modelData = [];
    for (const model of models) {
      modelData.push({
        id: model.name,
        object: 'model',
        created: Math.floor(new Date(model.createdAt).getTime() / 1000),
        owned_by: 'system',
      });
      
      if (model.alias && model.alias.trim() !== '') {
        modelData.push({
          id: model.alias,
          object: 'model',
          created: Math.floor(new Date(model.createdAt).getTime() / 1000),
          owned_by: 'system',
        });
      }
    }

    const responseData = {
      object: 'list',
      data: modelData,
    };

    return NextResponse.json(responseData, {
      headers: {
        'Cache-Control': 'no-store, no-cache, must-revalidate, proxy-revalidate',
        'Pragma': 'no-cache',
        'Expires': '0',
      },
    });
  } catch (error) {
    console.error("Error fetching models:", error);
    return NextResponse.json({ error: 'An internal server error occurred.' }, { status: 500 });
  }
}
