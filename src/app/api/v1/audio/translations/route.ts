import { NextResponse } from 'next/server';
import { PrismaClient } from '@prisma/client';

const prisma = new PrismaClient();

export async function POST(request: Request) {
  try {
    // 1. Authenticate the request
    const authHeader = request.headers.get('Authorization');
    if (!authHeader || !authHeader.startsWith('Bearer ')) {
      return NextResponse.json({ error: 'Unauthorized: Missing or invalid Authorization header' }, { status: 401 });
    }
    const apiKey = authHeader.split(' ')[1];
    const dbKey = await prisma.gatewayApiKey.findUnique({ where: { key: apiKey } });

    if (!dbKey || !dbKey.enabled) {
      return NextResponse.json({ error: 'Unauthorized: Invalid API Key' }, { status: 401 });
    }

    // Non-blocking update of lastUsed time
    prisma.gatewayApiKey.update({ where: { id: dbKey.id }, data: { lastUsed: new Date() } }).catch(console.error);

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
    const model = await prisma.model.findUnique({
      where: { name: modelName },
    });

    if (!model) {
      return NextResponse.json({ error: `Model '${modelName}' not found` }, { status: 404 });
    }

    // 4. Find the ModelRoute for the requested model and an available channel
    const modelRoute = await prisma.modelRoute.findFirst({
      where: {
        modelId: model.id,
        channel: { enabled: true },
      },
      include: {
        channel: {
          include: {
            provider: true,
          },
        },
      },
    });

    if (!modelRoute) {
      return NextResponse.json({ error: `No route configured for model '${modelName}'` }, { status: 404 });
    }

    const { channel } = modelRoute;
    const { provider } = channel;

    // 5. Forward the request to the upstream provider
    const targetUrl = `${provider.baseURL}/audio/translations`;

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
      const logEntry = await prisma.log.create({
        data: {
          latency: 0, // TODO: calculate latency
          promptTokens: 0,
          completionTokens: 0,
          totalTokens: 0,
          apiKeyId: dbKey.id,
          modelRouteId: modelRoute.id,
        },
      });
      await prisma.logDetail.create({
        data: {
          logId: logEntry.id,
          requestBody: requestBodyToLog,
          responseBody: responseData,
        },
      });
    } catch (logError) {
      console.error("Failed to log request:", logError);
    }

    return NextResponse.json(responseData);

  } catch (error) {
    console.error("Gateway Error:", error);
    return NextResponse.json({ error: 'An internal server error occurred.' }, { status: 500 });
  }
}
