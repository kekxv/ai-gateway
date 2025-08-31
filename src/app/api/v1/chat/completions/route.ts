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
    const originalRequestedModelName = requestBody.model; // Store the original requested model name
    const streamRequested = requestBody.stream === true; // Check for stream flag

    if (!originalRequestedModelName) {
      return NextResponse.json({ error: 'Missing \'model\' in request body' }, { status: 400 });
    }

    // 2. Find the Model by its name or alias
    const model = await db.get('SELECT * FROM Model WHERE name = ? OR alias = ?', originalRequestedModelName, originalRequestedModelName);

    if (!model) {
      return NextResponse.json({ error: `Model '${originalRequestedModelName}' not found` }, { status: 404 });
    }

    // IMPORTANT: Use the actual model name from the DB for upstream request
    const upstreamRequestBody = { ...requestBody, model: model.name };

    // 3. Find all eligible ModelRoutes for the requested model
    const eligibleModelRoutes = await db.all(
      `SELECT mr.*, c.name as channelName
       FROM ModelRoute mr
       JOIN Channel c ON mr.channelId = c.id
       WHERE mr.modelId = ? AND c.enabled = TRUE`,
      model.id
    );

    // For each eligible ModelRoute, fetch one associated provider
    for (const route of eligibleModelRoutes) {
      const channelProvider = await db.get(
        `SELECT cp.providerId, p.name, p.baseURL, p.apiKey
         FROM ChannelProvider cp
         JOIN Provider p ON cp.providerId = p.id
         WHERE cp.channelId = ?
         ORDER BY cp.providerId LIMIT 1`, // Pick one provider for routing
        route.channelId
      );

      if (!channelProvider) {
        // If a channel has no associated provider, this route is not truly eligible
        // We could filter it out or return an error. For now, let's skip it.
        console.warn(`Channel ${route.channelId} has no associated provider. Skipping route.`);
        route.channel = null; // Mark as ineligible
        continue;
      }

      route.channel = {
        name: route.channelName,
        provider: {
          name: channelProvider.name,
          baseURL: channelProvider.baseURL,
          apiKey: channelProvider.apiKey,
        },
      };
    }

    // Filter out routes that had no associated provider
    const finalEligibleModelRoutes = eligibleModelRoutes.filter(route => route.channel !== null);

    if (finalEligibleModelRoutes.length === 0) {
      return NextResponse.json({ error: `No enabled routes configured for model '${originalRequestedModelName}'` }, { status: 404 });
    }

    // Implement weighted random selection
    let totalWeight = 0;
    for (const route of finalEligibleModelRoutes) { // Use finalEligibleModelRoutes
      totalWeight += route.weight;
    }

    let randomWeight = Math.random() * totalWeight;
    let selectedModelRoute = null;

    for (const route of finalEligibleModelRoutes) { // Use finalEligibleModelRoutes
      randomWeight -= route.weight;
      if (randomWeight <= 0) {
        selectedModelRoute = route;
        break;
      }
    }

    if (!selectedModelRoute) {
      selectedModelRoute = finalEligibleModelRoutes[0];
    }

    // --- NEW: API Key Channel Permission Check ---
    if (!dbKey.bindToAllChannels) {
      const apiKeyChannel = await db.get(
        'SELECT 1 FROM GatewayApiKeyChannel WHERE apiKeyId = ? AND channelId = ?',
        dbKey.id,
        selectedModelRoute.channel.id
      );
      if (!apiKeyChannel) {
        return NextResponse.json({ error: `Unauthorized: API Key not bound to channel '${selectedModelRoute.channel.name}'` }, { status: 403 });
      }
    }
    // --- END NEW ---

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
      body: JSON.stringify(upstreamRequestBody),
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
            const result = await db.run(
              'INSERT INTO Log (latency, promptTokens, completionTokens, totalTokens, apiKeyId, modelRouteId) VALUES (?, ?, ?, ?, ?, ?)',
              latency,
              promptTokens,
              completionTokens,
              totalTokens,
              dbKey.id,
              selectedModelRoute.id
            );
            const logEntryId = result.lastID;

            await db.run(
              'INSERT INTO LogDetail (logId, requestBody) VALUES (?, ?)',
              logEntryId,
              JSON.stringify(requestBody)
            );
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
          const result = await db.run(
            'INSERT INTO Log (latency, promptTokens, completionTokens, totalTokens, apiKeyId, modelRouteId) VALUES (?, ?, ?, ?, ?, ?)',
            latency,
            responseData.usage.prompt_tokens,
            responseData.usage.completion_tokens,
            responseData.usage.total_tokens,
            dbKey.id,
            selectedModelRoute.id
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
      }

      return NextResponse.json(responseData);
    }

  } catch (error) {
    console.error("Gateway Error:", error);
    return NextResponse.json({ error: 'An internal server error occurred.' }, { status: 500 });
  }
}
