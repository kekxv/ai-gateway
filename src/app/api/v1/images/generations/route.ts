import { NextResponse } from 'next/server';
import { getInitializedDb } from '@/lib/db';

export async function POST(request: Request) {
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

    const requestBody = await request.json();
    const requestedModelName = requestBody.model;

    if (!requestedModelName) {
      // DALL-E 2 doesn't require a model parameter, so we can't enforce it here.
      // We'll just pass the body through.
    }

    // 2. Find a route for the request.
    // For image generation, the model is not always specified in the body,
    // so we need a different way to route the request.
    // A simple approach is to have a default image generation channel.
    // For now, we will find the first available channel that has a provider with "dall-e" in the name.
    // This is a temporary solution and should be improved with a more robust routing mechanism.
    const modelRoute = await db.get(
      `SELECT mr.*, m.name as modelName, c.name as channelName, p.name as providerName, p.baseURL, p.apiKey
       FROM ModelRoute mr
       JOIN Model m ON mr.modelId = m.id
       JOIN Channel c ON mr.channelId = c.id
       JOIN Provider p ON c.providerId = p.id
       WHERE m.name LIKE ? AND c.enabled = TRUE`,
      '%dall-e%'
    );

    if (modelRoute) {
      modelRoute.model = { name: modelRoute.modelName };
      modelRoute.channel = {
        name: modelRoute.channelName,
        provider: {
          name: modelRoute.providerName,
          baseURL: modelRoute.baseURL,
          apiKey: modelRoute.apiKey,
        },
      };
    }

    if (!modelRoute) {
      return NextResponse.json({ error: `No route configured for image generation` }, { status: 404 });
    }

    const { channel } = modelRoute;
    const { provider } = channel;

    // 3. Forward the request to the upstream provider
    const targetUrl = `${provider.baseURL}/images/generations`;
    const startTime = Date.now();

    const fetchOptions: RequestInit = {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${channel.provider.apiKey}`,
      },
      body: JSON.stringify(requestBody),
    };

    const upstreamResponse = await fetch(targetUrl, fetchOptions);
    const latency = Date.now() - startTime;

    // 4. Handle response
    if (!upstreamResponse.ok) {
      const errorData = await upstreamResponse.json();
      return NextResponse.json({ error: `上游服务错误: ${errorData.message || upstreamResponse.statusText}` }, { status: upstreamResponse.status});
    }
    const responseData = await upstreamResponse.json();

    // Log the request (no token usage for image generation)
    try {
      const result = await db.run(
        'INSERT INTO Log (latency, promptTokens, completionTokens, totalTokens, apiKeyId, modelRouteId) VALUES (?, ?, ?, ?, ?, ?)',
        latency,
        0,
        0,
        0,
        dbKey.id,
        modelRoute.id
      );
      const logEntryId = result.lastID;

      await db.run(
        'INSERT INTO LogDetail (logId, requestBody, responseBody) VALUES (?, ?, ?)',
        logEntryId,
        JSON.stringify(requestBody),
        JSON.stringify(responseData)
      );
    } catch (logError) {
      console.error("Failed to log request:", logError);
      // Don't block the response to the user
    }

    return NextResponse.json(responseData);

  } catch (error) {
    console.error("Gateway Error:", error);
    return NextResponse.json({ error: 'An internal server error occurred.' }, { status: 500 });
  }
}
