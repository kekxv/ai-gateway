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

    db.run('UPDATE GatewayApiKey SET lastUsed = ? WHERE id = ?', new Date().toISOString(), dbKey.id).catch(console.error);

    const requestBody = await request.json();
    const originalRequestedModelName = requestBody.model;

    if (!originalRequestedModelName) {
      return NextResponse.json({ error: "Missing 'model' in request body" }, { status: 400 });
    }

    const model = await db.get('SELECT * FROM Model WHERE name = ? OR alias = ?', originalRequestedModelName, originalRequestedModelName);
    if (!model) {
      return NextResponse.json({ error: `Model '${originalRequestedModelName}' not found` }, { status: 404 });
    }

    const upstreamRequestBody = { ...requestBody, model: model.name };

    const eligibleModelRoutes = await db.all(
      `SELECT mr.id, mr.weight, mr.modelId, p.id as providerId, p.name as providerName, p.baseURL, p.apiKey
       FROM ModelRoute mr
       JOIN Provider p ON mr.providerId = p.id
       WHERE mr.modelId = ?`,
      model.id
    );

    if (eligibleModelRoutes.length === 0) {
      return NextResponse.json({ error: `No enabled routes configured for model '${originalRequestedModelName}'` }, { status: 404 });
    }

    let totalWeight = 0;
    for (const route of eligibleModelRoutes) {
      totalWeight += route.weight;
    }
    let randomWeight = Math.random() * totalWeight;
    let selectedRoute = null;
    for (const route of eligibleModelRoutes) {
      randomWeight -= route.weight;
      if (randomWeight <= 0) {
        selectedRoute = route;
        break;
      }
    }
    if (!selectedRoute) {
      selectedRoute = eligibleModelRoutes[0];
    }

    // 5. API Key Permission Check (adapted for new channel rules)
    if (!dbKey.bindToAllChannels) {
      const requestedModelId = model.id;

      const apiKeyChannels = await db.all(
        'SELECT channelId FROM GatewayApiKeyChannel WHERE apiKeyId = ?',
        dbKey.id
      );
      const allowedChannelIds = apiKeyChannels.map((gac: any) => gac.channelId);

      if (allowedChannelIds.length === 0) {
        return NextResponse.json({ error: `Unauthorized: API Key is not bound to any channels.` }, { status: 403 });
      }

      const modelAllowed = await db.get(
        `SELECT 1 FROM ChannelAllowedModel WHERE modelId = ? AND channelId IN (${allowedChannelIds.map(() => '?').join(',')})`,
        requestedModelId,
        ...allowedChannelIds
      );

      if (!modelAllowed) {
        return NextResponse.json({ error: `Unauthorized: API Key does not have permission for the requested model.` }, { status: 403 });
      }
    }

    // 6. Billing Check (Initial)
    const user = await db.get('SELECT * FROM User WHERE id = ?', dbKey.userId);
    if (!user) {
      return NextResponse.json({ error: 'User not found for API Key' }, { status: 500 });
    }

    // If model has a cost, check if user has positive balance
    if ((model.inputTokenPrice > 0 || model.outputTokenPrice > 0) && user.balance <= 0) {
      return NextResponse.json({ error: 'Insufficient balance. Please top up your account.' }, { status: 403 });
    }

    const targetUrl = `${selectedRoute.baseURL}/embeddings`;
    const startTime = Date.now();

    const fetchOptions: RequestInit = {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${selectedRoute.apiKey}`,
      },
      body: JSON.stringify(upstreamRequestBody),
    };

    const upstreamResponse = await fetch(targetUrl, fetchOptions);
    const latency = Date.now() - startTime;

    if (!upstreamResponse.ok) {
      const errorData = await upstreamResponse.json();
      return NextResponse.json({ error: `Upstream service error: ${errorData.error?.message || upstreamResponse.statusText}` }, { status: upstreamResponse.status });
    }
    const responseData = await upstreamResponse.json();

    if (responseData.usage) {
      try {
        // Calculate cost
        const totalCost = Math.round(((responseData.usage.prompt_tokens / 1000) * model.inputTokenPrice + (responseData.usage.completion_tokens / 1000) * model.outputTokenPrice)); // Round to nearest integer (cents)

        // Only check balance and deduct if cost is greater than 0
        if (totalCost > 0) {
          // Fetch user again to get latest balance (important for concurrency)
          const currentUser = await db.get('SELECT balance FROM User WHERE id = ?', dbKey.userId); // Use dbKey.userId
          if (!currentUser || currentUser.balance < totalCost) {
            console.error(`User ${dbKey.userId} has insufficient balance (${currentUser?.balance}) for cost ${totalCost}.`);
          } else {
            // Deduct cost from user's balance
            await db.run('UPDATE User SET balance = balance - ? WHERE id = ?', totalCost, dbKey.userId);
          }
        }

        const result = await db.run(
          'INSERT INTO Log (latency, promptTokens, completionTokens, totalTokens, apiKeyId, modelName, providerName, cost) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
          latency, responseData.usage.prompt_tokens, responseData.usage.completion_tokens, responseData.usage.total_tokens, dbKey.id, model.name, selectedRoute.providerName, totalCost
        );
        const logEntryId = result.lastID;
        await db.run(
          'INSERT INTO LogDetail (logId, requestBody, responseBody) VALUES (?, ?, ?)',
          logEntryId, JSON.stringify(requestBody), JSON.stringify(responseData)
        );
      } catch (logError) {
        console.error("Failed to log request:", logError);
      }
    }

    return NextResponse.json(responseData);

  } catch (error) {
    console.error("Gateway Error:", error);
    return NextResponse.json({ error: 'An internal server error occurred.' }, { status: 500 });
  }
}
