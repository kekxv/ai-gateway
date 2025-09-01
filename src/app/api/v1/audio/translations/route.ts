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

    const formData = await request.formData();
    const file = formData.get('file') as File;
    const modelName = formData.get('model') as string;

    if (!file) {
      return NextResponse.json({ error: "Missing 'file' in request body" }, { status: 400 });
    }
    if (!modelName) {
      return NextResponse.json({ error: "Missing 'model' in request body" }, { status: 400 });
    }

    const model = await db.get('SELECT * FROM Model WHERE name = ? OR alias = ?', modelName, modelName);
    if (!model) {
      return NextResponse.json({ error: `Model '${modelName}' not found` }, { status: 404 });
    }

    const upstreamFormData = new FormData();
    for (const [key, value] of formData.entries()) {
        upstreamFormData.append(key, value as string);
    }
    upstreamFormData.set('model', model.name);

    const eligibleModelRoutes = await db.all(
      `SELECT mr.id, mr.weight, mr.modelId, p.id as providerId, p.name as providerName, p.baseURL, p.apiKey
       FROM ModelRoute mr
       JOIN Provider p ON mr.providerId = p.id
       WHERE mr.modelId = ?`,
      model.id
    );

    if (eligibleModelRoutes.length === 0) {
      return NextResponse.json({ error: `No enabled routes configured for model '${modelName}'` }, { status: 404 });
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

    // Simple initial balance check: ensure user has some positive balance
    if ((model.inputTokenPrice > 0 || model.outputTokenPrice > 0) && user.balance <= 0) {
      return NextResponse.json({ error: 'Insufficient balance. Please top up your account.' }, { status: 403 });
    }

    const targetUrl = `${selectedRoute.baseURL}/audio/translations`;
    const startTime = Date.now();

    const fetchOptions: RequestInit = {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${selectedRoute.apiKey}` },
      body: upstreamFormData,
    };

    const upstreamResponse = await fetch(targetUrl, fetchOptions);
    const latency = Date.now() - startTime;

    if (!upstreamResponse.ok) {
      const errorData = await upstreamResponse.json();
      return NextResponse.json({ error: `Upstream service error: ${errorData.error?.message || upstreamResponse.statusText}` }, { status: upstreamResponse.status });
    }
    const responseData = await upstreamResponse.json();

    try {
      // Calculate cost (assuming fixed cost per audio translation request, using inputTokenPrice as the rate)
      const totalCost = Math.round(model.inputTokenPrice); // Assuming inputTokenPrice is the cost per request in cents

      // Initialize channel owner variables
      let ownerChannelId = null;
      let ownerChannelUserId = null;

      // Only check balance and deduct if cost is greater than 0
      if (totalCost > 0) {
        // Fetch user again to get latest balance (important for concurrency)
        const currentUser = await db.get('SELECT balance FROM User WHERE id = ?', dbKey.userId); // Use dbKey.userId
        if (!currentUser || currentUser.balance < totalCost) {
          console.error(`User ${dbKey.userId} has insufficient balance (${currentUser?.balance}) for cost ${totalCost}.`);
        } else {
          // Deduct cost from user's balance only if they are not the channel owner
          let shouldDeduct = true;
          
          // Check if the model route is associated with a shared channel
          // Find the channel that allows this model and is associated with the API key
          if (!dbKey.bindToAllChannels) {
            const apiKeyChannels = await db.all(
              'SELECT channelId FROM GatewayApiKeyChannel WHERE apiKeyId = ?',
              dbKey.id
            );
            const allowedChannelIds = apiKeyChannels.map((gac: any) => gac.channelId);
            
            if (allowedChannelIds.length > 0) {
              const channelModel = await db.get(
                `SELECT c.id as channelId, c.userId as channelUserId, c.shared as channelShared
                 FROM Channel c
                 JOIN ChannelAllowedModel cam ON c.id = cam.channelId
                 WHERE cam.modelId = ? AND c.id IN (${allowedChannelIds.map(() => '?').join(',')}) AND c.shared = 1
                 LIMIT 1`,
                model.id,
                ...allowedChannelIds
              );
              
              if (channelModel) {
                ownerChannelId = channelModel.channelId;
                ownerChannelUserId = channelModel.channelUserId;
                
                // If user is the channel owner, don't deduct balance
                if (ownerChannelUserId === dbKey.userId) {
                  shouldDeduct = false;
                }
              }
            }
          } else {
            // When bound to all channels, check if there's a shared channel that allows this model
            const channelModel = await db.get(
              `SELECT c.id as channelId, c.userId as channelUserId, c.shared as channelShared
               FROM Channel c
               JOIN ChannelAllowedModel cam ON c.id = cam.channelId
               WHERE cam.modelId = ? AND c.shared = 1
               LIMIT 1`,
              model.id
            );
            
            if (channelModel) {
              ownerChannelId = channelModel.channelId;
              ownerChannelUserId = channelModel.channelUserId;
              
              // If user is the channel owner, don't deduct balance
              if (ownerChannelUserId === dbKey.userId) {
                shouldDeduct = false;
              }
            }
          }
          
          // Deduct cost from user's balance if they are not the channel owner
          if (shouldDeduct) {
            await db.run('UPDATE User SET balance = balance - ? WHERE id = ?', totalCost, dbKey.userId);
          }
          
          // If we found a shared channel and user is not the owner, distribute the cost
          if (ownerChannelId && ownerChannelUserId && ownerChannelUserId !== dbKey.userId) {
            // Add cost to channel owner's balance
            await db.run('UPDATE User SET balance = balance + ? WHERE id = ?', totalCost, ownerChannelUserId);
          }
        }
      }

      const result = await db.run(
        'INSERT INTO Log (latency, promptTokens, completionTokens, totalTokens, apiKeyId, modelName, providerName, cost, ownerChannelId, ownerChannelUserId) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        latency, 0, 0, 0, dbKey.id, model.name, selectedRoute.providerName, totalCost, ownerChannelId, ownerChannelUserId
      );
      const logEntryId = result.lastID;
      const requestBodyToLog: Record<string, any> = {};
      for (const [key, value] of formData.entries()) {
        if (key !== 'file') { requestBodyToLog[key] = value; }
      }
      await db.run(
        'INSERT INTO LogDetail (logId, requestBody, responseBody) VALUES (?, ?, ?)',
        logEntryId, JSON.stringify(requestBodyToLog), JSON.stringify(responseData)
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
