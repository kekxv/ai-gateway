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

    // 2. Parse the multipart/form-data request
    const formData = await request.formData();
    const image = formData.get('image') as File;
    const prompt = formData.get('prompt') as string;

    const requestBodyToLog: Record<string, any> = {};
    for (const [key, value] of formData.entries()) {
        if (key !== 'image') { // Exclude the image file itself
            requestBodyToLog[key] = value;
        }
    }

    if (!image) {
      return NextResponse.json({ error: 'Missing \'image\' in request body' }, { status: 400 });
    }
    if (!prompt) {
      return NextResponse.json({ error: 'Missing \'prompt\' in request body' }, { status: 400 });
    }

    // 3. Find a route for the request.
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

    // 4. Forward the request to the upstream provider
    const targetUrl = `${provider.baseURL}/images/edits`;

    const upstreamFormData = new FormData();
    upstreamFormData.append('image', image, image.name);
    upstreamFormData.append('prompt', prompt);
    // Append other fields from the original request if they exist
    for (const [key, value] of formData.entries()) {
        if (key !== 'image' && key !== 'prompt') {
            upstreamFormData.append(key, value as string);
        }
    }

    const fetchOptions: RequestInit = {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${channel.provider.apiKey}`,
      },
      body: upstreamFormData,
    };

    const upstreamResponse = await fetch(targetUrl, fetchOptions);

    // 5. Handle response
    if (!upstreamResponse.ok) {
      const errorData = await upstreamResponse.json();
      return NextResponse.json({ error: `上游服务错误: ${errorData.message || upstreamResponse.statusText}` }, { status: upstreamResponse.status});
    }
    const responseData = await upstreamResponse.json();

    // Log the request
    try {
      const result = await db.run(
        'INSERT INTO Log (latency, promptTokens, completionTokens, totalTokens, apiKeyId, modelRouteId) VALUES (?, ?, ?, ?, ?, ?)',
        0, // TODO: calculate latency
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
        JSON.stringify(requestBodyToLog),
        JSON.stringify(responseData)
      );
    } catch (logError) {
      console.error("Failed to log request:", logError);
    }

    return NextResponse.json(responseData);

  } catch (error) {
    console.error("Gateway Error:", error);
    return NextResponse.json({ error: 'An internal server error occurred.' }, { status: 500 });
  }
}
