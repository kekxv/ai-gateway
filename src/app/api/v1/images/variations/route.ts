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
    const image = formData.get('image') as File;

    const requestBodyToLog: Record<string, any> = {};
    for (const [key, value] of formData.entries()) {
        if (key !== 'image') { // Exclude the image file itself
            requestBodyToLog[key] = value;
        }
    }

    if (!image) {
      return NextResponse.json({ error: 'Missing \'image\' in request body' }, { status: 400 });
    }

    // 3. Find a route for the request.
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

    // 4. Forward the request to the upstream provider
    const targetUrl = `${provider.baseURL}/images/variations`;

    const upstreamFormData = new FormData();
    upstreamFormData.append('image', image, image.name);
    // Append other fields from the original request if they exist
    for (const [key, value] of formData.entries()) {
        if (key !== 'image') {
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
      await prisma.log.create({
        data: {
          latency: 0, // TODO: calculate latency
          promptTokens: 0,
          completionTokens: 0,
          totalTokens: 0,
          apiKeyId: dbKey.id,
          modelRouteId: modelRoute.id,
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
