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
    const streamRequested = requestBody.stream === true; // Check for stream flag

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

    // 3. Find all eligible ModelRoutes for the requested model
    const eligibleModelRoutes = await prisma.modelRoute.findMany({
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

    if (eligibleModelRoutes.length === 0) {
      return NextResponse.json({ error: `No enabled routes configured for model '${requestedModelName}'` }, { status: 404 });
    }

    // Implement weighted random selection
    let totalWeight = 0;
    for (const route of eligibleModelRoutes) {
      totalWeight += route.weight;
    }

    let randomWeight = Math.random() * totalWeight;
    let selectedModelRoute = null;

    for (const route of eligibleModelRoutes) {
      randomWeight -= route.weight;
      if (randomWeight <= 0) {
        selectedModelRoute = route;
        break;
      }
    }

    if (!selectedModelRoute) {
      // Fallback in case of floating point issues or if all weights are 0 (though we should prevent that)
      selectedModelRoute = eligibleModelRoutes[0];
    }

    const { channel } = selectedModelRoute;
    const { provider } = channel;

    // 4. Forward the request to the upstream provider
    const targetUrl = `${provider.baseURL}/chat/completions`;
    const startTime = Date.now();

    const fetchOptions: RequestInit = {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${channel.provider.apiKey}`,
      },
      body: JSON.stringify(requestBody),
    };

    if (streamRequested) {
      // @ts-expect-error - duplex is required for streaming in Node.js
      fetchOptions.duplex = 'half'; // Required for streaming in Node.js
    }

    const upstreamResponse = await fetch(targetUrl, fetchOptions);
    const latency = Date.now() - startTime;

    // 5. Handle response based on stream flag
    if (streamRequested) {
      if (!upstreamResponse.body) {
        return NextResponse.json({ error: "Upstream service returned no response body." }, { status: 502 });
      }

      const [logStream, clientStream] = upstreamResponse.body.tee();

      // Asynchronously process the log stream
      (async () => {
        let promptTokens = 0;
        let completionTokens = 0;
        let totalTokens = 0;
        const reader = logStream.getReader();
        const decoder = new TextDecoder();

        try {
          while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            const chunk = decoder.decode(value, { stream: true });
            const lines = chunk.split('\n').filter(line => line.startsWith('data: '));

            for (const line of lines) {
              const jsonStr = line.substring(6);
              if (jsonStr.trim() === '[DONE]') continue;
              try {
                const jsonObj = JSON.parse(jsonStr);
                if (jsonObj.usage) {
                  promptTokens = jsonObj.usage.prompt_tokens || 0;
                  completionTokens = jsonObj.usage.completion_tokens || 0;
                  totalTokens = jsonObj.usage.total_tokens || 0;
                }
              } catch (e) {
                // Ignore parsing errors
              }
            }
          }

          if (totalTokens > 0) {
            await prisma.log.create({
              data: {
                latency,
                promptTokens,
                completionTokens,
                totalTokens,
                apiKeyId: dbKey.id,
                modelRouteId: selectedModelRoute.id,
                requestBody: requestBody,
              },
            });
          }
        } catch (logError) {
          console.error("Failed to log streaming request:", logError);
        }
      })();

      return new Response(clientStream, {
        headers: {
          'Content-Type': upstreamResponse.headers.get('Content-Type') || 'text/plain',
        },
        status: upstreamResponse.status,
      });
    } else {
      // Non-streaming response
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
              modelRouteId: selectedModelRoute.id,
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
    }

  } catch (error) {
    console.error("Gateway Error:", error);
    return NextResponse.json({ error: 'An internal server error occurred.' }, { status: 500 });
  }
}
