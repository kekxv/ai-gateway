import { NextResponse } from 'next/server';
import { getInitializedDb } from '@/lib/db';
import { authenticateRequest } from '../_lib/gateway-helpers';

export async function GET(request: Request) {
  try {
    const db = await getInitializedDb();

    const { apiKeyData: dbKey, errorResponse: authError } = await authenticateRequest(request as any, db);
    if (authError) return authError;

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
