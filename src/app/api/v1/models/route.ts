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

    // Get models associated with channels linked to this API key
    let models;
    if (dbKey.bindToAllChannels) {
      // If API key is bound to all channels, return all models
      models = await db.all(`
        SELECT DISTINCT m.* 
        FROM Model m
        JOIN ProviderModel pm ON m.id = pm.modelId
        JOIN ModelRoute mr ON m.id = mr.modelId
        JOIN Channel c ON mr.channelId = c.id
        WHERE c.enabled = 1
      `);
    } else {
      // If API key is bound to specific channels, return only models from those channels
      models = await db.all(`
        SELECT DISTINCT m.* 
        FROM Model m
        JOIN ProviderModel pm ON m.id = pm.modelId
        JOIN ModelRoute mr ON m.id = mr.modelId
        JOIN Channel c ON mr.channelId = c.id
        JOIN GatewayApiKeyChannel gakc ON c.id = gakc.channelId
        WHERE gakc.apiKeyId = ? AND c.enabled = 1
      `, dbKey.id);
    }

    const modelData = [];
    for (const model of models) {
      // Add the original model
      modelData.push({
        id: model.name,
        object: 'model',
        created: Math.floor(new Date(model.createdAt).getTime() / 1000),
        owned_by: 'system',
      });
      
      // If the model has an alias, add it as a separate entry
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
