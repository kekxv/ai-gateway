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

    const requestBody = await request.json();
    const requestedModelName = requestBody.model;

    if (!requestedModelName) {
      return NextResponse.json({ error: 'Missing \'model\' in request body' }, { status: 400 });
    }

    // 2. Find the Model by its name
    const model = await prisma.model.findUnique({
      where: { name: requestedModelName },
    });

    if (!model) {
      return NextResponse.json({ error: `Model '${requestedModelName}' not found` }, { status: 404 });
    }

    // 3. Find the ModelRoute for the requested model and an available channel
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
      return NextResponse.json({ error: `No route configured for model '${requestedModelName}'` }, { status: 404 });
    }

    const { channel } = modelRoute;
    const { provider } = channel;

    // 4. Forward the request to the upstream provider
    const targetUrl = `${provider.baseURL}/embeddings`;
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

    // 5. Handle response
    if (!upstreamResponse.ok) {
      const errorData = await upstreamResponse.json();
      return NextResponse.json({ error: `上游服务错误: ${errorData.message || upstreamResponse.statusText}` }, { status: upstreamResponse.status});
    }
    const responseData = await upstreamResponse.json();

    // Log the request
    if (responseData.usage) {
      try {
        await prisma.log.create({
          data: {
            latency,
            promptTokens: responseData.usage.prompt_tokens,
            completionTokens: responseData.usage.completion_tokens,
            totalTokens: responseData.usage.total_tokens,
            apiKeyId: dbKey.id,
            modelRouteId: modelRoute.id,
            requestBody: requestBody,
            responseBody: responseData,
          },
        });
      } catch (logError) {
        console.error("Failed to log request:", logError);
        // Don't block the response to the user
      }
    }

    return NextResponse.json(responseData);

  } catch (error) {
    console.error("Gateway Error:", error);
    return NextResponse.json({ error: 'An internal server error occurred.' }, { status: 500 });
  }
}
