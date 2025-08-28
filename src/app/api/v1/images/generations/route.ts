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
      // DALL-E 2 doesn't require a model parameter, so we can't enforce it here.
      // We'll just pass the body through.
    }

    // 2. Find a route for the request.
    // For image generation, the model is not always specified in the body,
    // so we need a different way to route the request.
    // A simple approach is to have a default image generation channel.
    // For now, we will find the first available channel that has a provider with "dall-e" in the name.
    // This is a temporary solution and should be improved with a more robust routing mechanism.
    const modelRoute = await prisma.modelRoute.findFirst({
      where: {
        model: {
          name: {
            contains: 'dall-e',
          },
        },
        channel: { enabled: true },
      },
      include: {
        channel: {
          include: {
            provider: true,
          },
        },
        model: true,
      },
    });

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
      const logEntry = await prisma.log.create({
        data: {
          latency,
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
          requestBody: requestBody,
          responseBody: responseData,
        },
      });
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
