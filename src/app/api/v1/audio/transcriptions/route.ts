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
    const file = formData.get('file') as File;
    const modelName = formData.get('model') as string;

    const requestBodyToLog: Record<string, any> = {};
    for (const [key, value] of formData.entries()) {
        if (key !== 'file') { // Exclude the file itself
            requestBodyToLog[key] = value;
        }
    }

    if (!file) {
      return NextResponse.json({ error: 'Missing \'file\' in request body' }, { status: 400 });
    }
    if (!modelName) {
      return NextResponse.json({ error: 'Missing \'model\' in request body' }, { status: 400 });
    }

    // 3. Find the Model by its name
    const model = await db.get('SELECT * FROM Model WHERE name = ?', modelName);

    if (!model) {
      return NextResponse.json({ error: `Model '${modelName}' not found` }, { status: 404 });
    }

    // 4. Find the ModelRoute for the requested model and an available channel
    const modelRoute = await db.get(
      `SELECT mr.*, c.name as channelName, p.name as providerName, p.baseURL, p.apiKey
       FROM ModelRoute mr
       JOIN Channel c ON mr.channelId = c.id
       JOIN Provider p ON c.providerId = p.id
       WHERE mr.modelId = ? AND c.enabled = TRUE`,
      model.id
    );

    if (modelRoute) {
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
      return NextResponse.json({ error: `No route configured for model '${modelName}'` }, { status: 404 });
    }

    const { channel } = modelRoute;
    const { provider } = channel;

    // 5. Forward the request to the upstream provider
    const targetUrl = `${provider.baseURL}/audio/transcriptions`;

    const upstreamFormData = new FormData();
    upstreamFormData.append('file', file, file.name);
    upstreamFormData.append('model', modelName);
    // Append other fields from the original request if they exist
    for (const [key, value] of formData.entries()) {
        if (key !== 'file' && key !== 'model') {
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

    // 6. Handle response
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
