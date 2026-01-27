import {NextRequest, NextResponse} from 'next/server';
import {Database} from 'sqlite';
import {gzipSync} from 'zlib';

const errorCodesToDisable = [429];

// Define a consistent structure for our authentication result
type AuthResult = {
  apiKeyData: any;
  errorResponse: NextResponse | null;
};

/**
 * Authenticates a request by validating the API key.
 * @param request - The incoming NextRequest.
 * @param db - The database instance.
 * @returns An object containing either the apiKeyData or an errorResponse.
 */
export async function authenticateRequest(request: NextRequest, db: Database): Promise<AuthResult> {
  try {
    const authHeader = request.headers.get('Authorization');
    if (!authHeader || !authHeader.startsWith('Bearer ')) {
      console.error('[AUTH] Missing or invalid Authorization header');
      return {
        apiKeyData: null,
        errorResponse: NextResponse.json(
          {error: 'Unauthorized: Missing or invalid Authorization header'},
          {status: 401}
        ),
      };
    }

    const apiKey = authHeader.split(' ')[1];
    const apiKeyData = await db.get('SELECT * FROM GatewayApiKey WHERE key = ?', apiKey);

    if (!apiKeyData || !apiKeyData.enabled) {
      console.warn('[AUTH] Invalid or disabled API Key:', apiKey.substring(0, 10) + '...');
      return {
        apiKeyData: null,
        errorResponse: NextResponse.json({error: 'Unauthorized: Invalid API Key'}, {status: 401}),
      };
    }

    // Non-blocking update of lastUsed time
    db.run('UPDATE GatewayApiKey SET lastUsed = ? WHERE id = ?', new Date().toISOString(), apiKeyData.id).catch(
      (err) => console.error('[AUTH] Failed to update lastUsed:', err)
    );

    return {apiKeyData, errorResponse: null};
  } catch (err) {
    console.error('[AUTH] Database error during authentication:', err);
    return {
      apiKeyData: null,
      errorResponse: NextResponse.json({error: 'Authentication service error'}, {status: 500}),
    };
  }
}

/**
 * Finds a model by its name or alias.
 * If the model name does not contain a ':', it prefers a version with the ':latest' tag.
 * @param modelName - The name or alias of the model.
 * @param db - The database instance.
 * @returns The model data or null if not found.
 */
export async function findModel(modelName: string, db: Database): Promise<any> {
  try {
    if (modelName.includes(':')) {
      return await db.get('SELECT * FROM Model WHERE (name = ? OR alias = ?)', modelName, modelName);
    }

    const modelNameWithLatest = `${modelName}:latest`;
    return await db.get(
      `SELECT * FROM Model
       WHERE ((name = ? OR alias = ?) OR (name = ? OR alias = ?))
       ORDER BY INSTR(name, ':') DESC, name DESC`,
      modelName,
      modelName,
      modelNameWithLatest,
      modelNameWithLatest
    );
  } catch (err) {
    console.error('[MODEL] Error finding model:', modelName, err);
    return null;
  }
}

/**
 * Selects an upstream route for a given model using weighted random selection.
 * @param modelId - The ID of the model.
 * @param db - The database instance.
 * @returns The selected route data or null if no routes are available.
 */
export async function selectUpstreamRoute(modelId: number, db: Database): Promise<any> {
  try {
    const eligibleModelRoutes = await db.all(
      `SELECT mr.id, mr.weight, mr.modelId, p.id as providerId, p.name as providerName, p.baseURL, p.apiKey
       FROM ModelRoute mr
              JOIN Provider p ON mr.providerId = p.id
       WHERE mr.modelId = ?
         AND p.disabled = FALSE
         AND mr.disabled = FALSE
         AND (mr.disabledUntil IS NULL OR mr.disabledUntil < datetime('now'))`,
      modelId
    );

    if (eligibleModelRoutes.length === 0) {
      console.warn('[ROUTE] No eligible routes found for model:', modelId);
      return null;
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

    console.log('[ROUTE] Selected route:', {provider: selectedRoute.providerName, modelId, baseURL: selectedRoute.baseURL});
    return selectedRoute;
  } catch (err) {
    console.error('[ROUTE] Error selecting upstream route for model:', modelId, err);
    return null;
  }
}

/**
 * Checks if an API key has permission to use a specific model.
 * @param apiKeyData - The API key data from the database.
 * @param modelId - The ID of the model being requested.
 * @param db - The database instance.
 * @returns A NextResponse if permission is denied, otherwise null.
 */
export async function checkApiKeyPermission(
  apiKeyData: any,
  modelId: number,
  db: Database
): Promise<NextResponse | null> {
  try {
    if (apiKeyData.bindToAllChannels) {
      return null; // Key is bound to all channels, so permission is granted.
    }

    const apiKeyChannels = await db.all(
      'SELECT channelId FROM GatewayApiKeyChannel WHERE apiKeyId = ?',
      apiKeyData.id
    );
    const allowedChannelIds = apiKeyChannels.map((gac: any) => gac.channelId);

    if (allowedChannelIds.length === 0) {
      console.warn('[PERMISSION] API Key not bound to any channels:', apiKeyData.id);
      return NextResponse.json(
        {error: `Unauthorized: API Key is not bound to any channels.`},
        {status: 403}
      );
    }

    const modelAllowed = await db.get(
      `SELECT 1
       FROM ChannelAllowedModel
       WHERE modelId = ?
         AND channelId IN (${allowedChannelIds.map(() => '?').join(',')})`,
      modelId,
      ...allowedChannelIds
    );

    if (!modelAllowed) {
      console.warn('[PERMISSION] API Key lacks model access:', {apiKeyId: apiKeyData.id, modelId});
      return NextResponse.json(
        {error: `Unauthorized: API Key does not have permission for the requested model.`},
        {status: 403}
      );
    }

    return null; // Permission granted
  } catch (err) {
    console.error('[PERMISSION] Error checking API key permission:', err);
    return NextResponse.json({error: 'Permission check failed'}, {status: 500});
  }
}

/**
 * Performs an initial balance check for the user associated with the API key.
 * @param apiKeyData - The API key data from the database.
 * @param modelData - The model data from the database.
 * @param db - The database instance.
 * @returns A NextResponse if the balance is insufficient, otherwise null.
 */
export async function checkInitialBalance(
  apiKeyData: any,
  modelData: any,
  db: Database
): Promise<NextResponse | null> {
  try {
    const user = await db.get('SELECT * FROM User WHERE id = ?', apiKeyData.userId);
    if (!user) {
      console.error('[BALANCE] User not found for API Key:', apiKeyData.id);
      return NextResponse.json({error: 'User not found for API Key'}, {status: 500});
    }

    // If model has a cost, check if user has a positive balance.
    if ((modelData.inputTokenPrice > 0 || modelData.outputTokenPrice > 0) && user.balance <= 0) {
      console.warn('[BALANCE] Insufficient balance for user:', {userId: apiKeyData.userId, balance: user.balance, modelId: modelData.id});
      return NextResponse.json({error: 'Insufficient balance. Please top up your account.'}, {status: 403});
    }

    return null; // Balance is sufficient
  } catch (err) {
    console.error('[BALANCE] Error checking balance:', err);
    return NextResponse.json({error: 'Balance check failed'}, {status: 500});
  }
}

async function shouldDisableRoute(db: Database, selectedRoute: any): Promise<boolean> {
  // 1. Count total enabled models
  const totalModelsResult = await db.get("SELECT COUNT(*) as count FROM Model");
  const totalModels = totalModelsResult.count;

  if (totalModels <= 1) {
    return false; // Don't disable if there's only one or zero models
  }

  // 2. Count enabled routes for this model
  const modelRoutesResult = await db.get(
    "SELECT COUNT(*) as count FROM ModelRoute WHERE modelId = ? AND disabled = FALSE AND (disabledUntil IS NULL OR disabledUntil < datetime('now'))",
    selectedRoute.modelId
  );
  const totalModelRoutes = modelRoutesResult.count;

  if (totalModelRoutes <= 1) {
    return false; // Don't disable if it's the last route for the model
  }

  return true; // OK to disable
}

/**
 * Forwards a request to the upstream provider and handles the response.
 * @param targetUrl - The URL of the upstream service.
 * @param upstreamRequestBody - The body of the request to forward.
 * @param selectedRoute - The selected upstream route.
 * @param streamRequested - Whether the client requested a streaming response.
 * @returns A NextResponse object with the upstream response.
 */
export async function handleUpstreamRequest(
  db: Database,
  apiKeyData: any,
  model: any,
  selectedRoute: any,
  requestBody: any,
  targetUrl: string,
  streamRequested: boolean
): Promise<NextResponse> {
  const startTime = Date.now();
  const fetchOptions: RequestInit = {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${selectedRoute.apiKey}`,
    },
    body: JSON.stringify(requestBody),
  };

  if (streamRequested) {
    // @ts-expect-error - duplex is required for streaming in Node.js
    fetchOptions.duplex = 'half';
  }

  try {
    console.log('[UPSTREAM] Sending request to:', targetUrl, '| Stream:', streamRequested);
    const upstreamResponse = await fetch(targetUrl, fetchOptions);
    const latency = Date.now() - startTime;
    console.log('[UPSTREAM] Response received - Status:', upstreamResponse.status, '| Latency:', latency + 'ms');

    // Handle error responses from upstream for both streaming and non-streaming
    if (!upstreamResponse.ok) {
      console.error('[UPSTREAM] Error response from upstream:', {
        status: upstreamResponse.status,
        statusText: upstreamResponse.statusText,
        provider: selectedRoute.providerName,
        model: model.name,
        latency: latency
      });

      if (errorCodesToDisable.includes(upstreamResponse.status)) {
        if (await shouldDisableRoute(db, selectedRoute)) {
          const tenMinutesLater = new Date(Date.now() + 10 * 60 * 1000).toISOString();
          db.run('UPDATE ModelRoute SET disabledUntil = ? WHERE id = ?', tenMinutesLater, selectedRoute.id).catch(
            (err) => console.error('[UPSTREAM] Failed to disable route:', err)
          );
        }
      }

      const errorText = await upstreamResponse.text();
      let errorMessage = "Upstream service error: Provider returned error";
      try {
        const errorData = JSON.parse(errorText);
        if (errorData.error && errorData.error.message) {
          errorMessage = `Upstream service error: ${errorData.error.message}`;
        }
      } catch (_e) {
        if (errorText.trim()) {
          errorMessage = `Upstream service error: ${errorText.substring(0, 200)}`;
        }
      }
      
      // Log error response
      try {
        await db.run(
          'INSERT INTO Log (latency, promptTokens, completionTokens, totalTokens, apiKeyId, modelName, providerName, cost, ownerChannelId, ownerChannelUserId) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
          latency, 0, 0, 0, apiKeyData.id, model.name, selectedRoute.providerName, 0, null, null
        );
      } catch (logError) {
        console.error('[LOG] Failed to log error request:', logError);
      }
      
      return NextResponse.json({error: errorMessage}, {status: upstreamResponse.status});
    }

    if (streamRequested) {
      if (!upstreamResponse.body) {
        console.error('[UPSTREAM] Stream response has no body');
        return NextResponse.json({error: "Upstream service returned no response body."}, {status: 502});
      }
      // Log streaming request (with null values for tokens since we can't extract them from stream)
      try {
        console.log('[STREAMING] Logging stream request for model:', model.name);
        await db.run(
          'INSERT INTO Log (latency, promptTokens, completionTokens, totalTokens, apiKeyId, modelName, providerName, cost, ownerChannelId, ownerChannelUserId) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
          latency, 0, 0, 0, apiKeyData.id, model.name, selectedRoute.providerName, 0, null, null
        );
      } catch (logError) {
        console.error('[LOG] Failed to log streaming request:', logError);
      }
      
      // Return streaming response
      return new NextResponse(upstreamResponse.body, {
        headers: {'Content-Type': upstreamResponse.headers.get('Content-Type') || 'text/plain'},
        status: upstreamResponse.status,
      });
    } else {
      const responseData = await upstreamResponse.json();
      console.log('[RESPONSE] Success from upstream:', {model: model.name, provider: selectedRoute.providerName, latency: latency});
      await logRequestAndCalculateCost(db, apiKeyData, model, selectedRoute, requestBody, responseData, latency, false);
      return NextResponse.json(responseData);
    }
  } catch (err) {
    console.error('[UPSTREAM] Fatal error in handleUpstreamRequest:', {error: err, targetUrl, model: model.name});
    return NextResponse.json({error: 'Upstream request failed'}, {status: 502});
  }
}

export async function handleUpstreamFormRequest(
  db: Database,
  apiKeyData: any,
  model: any,
  selectedRoute: any,
  formData: FormData,
  targetUrl: string,
) {
  const startTime = Date.now();
  const fetchOptions: RequestInit = {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${selectedRoute.apiKey}`,
    },
    body: formData,
  };

  const upstreamResponse = await fetch(targetUrl, fetchOptions);
  const latency = Date.now() - startTime;
  console.log('[FORM_REQUEST] Response received - Status:', upstreamResponse.status, '| Latency:', latency + 'ms');

  if (!upstreamResponse.ok) {
    console.error('[FORM_REQUEST] Error response from upstream:', {
      status: upstreamResponse.status,
      statusText: upstreamResponse.statusText,
      provider: selectedRoute.providerName,
      model: model.name
    });

    if (errorCodesToDisable.includes(upstreamResponse.status)) {
      if (await shouldDisableRoute(db, selectedRoute)) {
        const tenMinutesLater = new Date(Date.now() + 10 * 60 * 1000).toISOString();
        db.run('UPDATE ModelRoute SET disabledUntil = ? WHERE id = ?', tenMinutesLater, selectedRoute.id).catch(
          (err) => console.error('[FORM_REQUEST] Failed to disable route:', err)
        );
      }
    }

    // Log error response
    try {
      await db.run(
        'INSERT INTO Log (latency, promptTokens, completionTokens, totalTokens, apiKeyId, modelName, providerName, cost, ownerChannelId, ownerChannelUserId) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        latency, 0, 0, 0, apiKeyData.id, model.name, selectedRoute.providerName, 0, null, null
      );
    } catch (logError) {
      console.error('[LOG] Failed to log form request error:', logError);
    }

    const errorData = await upstreamResponse.json();
    return NextResponse.json({error: `Upstream service error: ${errorData.error?.message || upstreamResponse.statusText}`}, {status: upstreamResponse.status});
  }
  const responseData = await upstreamResponse.json();
  console.log('[FORM_REQUEST] Success:', {model: model.name, provider: selectedRoute.providerName, latency});

  await logRequestAndCalculateCost(db, apiKeyData, model, selectedRoute, {}, responseData, latency, false);

  return NextResponse.json(responseData);
}

export async function findRouteForModelPattern(pattern: string, db: Database): Promise<any> {
  const models = await db.all(`SELECT *
                               FROM Model
                               WHERE name LIKE ?`, pattern);
  if (models.length === 0) {
    return null;
  }
  const modelIds = models.map((m: { id: number }) => m.id);

  const eligibleModelRoutes = await db.all(
    `SELECT mr.id, mr.weight, mr.modelId, p.id as providerId, p.name as providerName, p.baseURL, p.apiKey
     FROM ModelRoute mr
            JOIN Provider p ON mr.providerId = p.id
     WHERE mr.modelId IN (${modelIds.map(() => '?').join(',')})
       AND p.disabled = FALSE
       AND mr.disabled = FALSE
       AND (mr.disabledUntil IS NULL OR mr.disabledUntil < datetime('now'))`,
    ...modelIds
  );

  if (eligibleModelRoutes.length === 0) {
    return null;
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

  return selectedRoute;
}

export async function logRequestAndCalculateCost(
  db: Database,
  apiKeyData: any,
  model: any,
  selectedRoute: any,
  requestBody: any,
  responseData: any,
  latency: number,
  streamed: boolean,
) {
  console.log('[LOG] Starting to log request:', {model: model.name, apiKeyId: apiKeyData.id, latency});
  try {
    let promptTokens = 0;
    let completionTokens = 0;
    let totalTokens = 0;

    // Extract token information from response
    if (responseData && typeof responseData === 'object') {
      if (responseData.usage) {
        promptTokens = responseData.usage.prompt_tokens || 0;
        completionTokens = responseData.usage.completion_tokens || 0;
        totalTokens = responseData.usage.total_tokens || 0;
      }
    }

    const totalCost = Math.round(((promptTokens / 1000) * model.inputTokenPrice + (completionTokens / 1000) * model.outputTokenPrice));

    // Determine owner channel information
    let ownerChannelId = null;
    let ownerChannelUserId = null;

    if (!apiKeyData.bindToAllChannels) {
      const apiKeyChannels = await db.all(
        'SELECT channelId FROM GatewayApiKeyChannel WHERE apiKeyId = ?',
        apiKeyData.id
      );
      const allowedChannelIds = apiKeyChannels.map((gac: any) => gac.channelId);
      if (allowedChannelIds.length > 0) {
        const channelModel = await db.get(
          `SELECT c.id as channelId, c.userId as channelUserId, c.shared as channelShared
           FROM Channel c
                  JOIN ChannelAllowedModel cam ON c.id = cam.channelId
           WHERE cam.modelId = ?
             AND c.id IN (${allowedChannelIds.map(() => '?').join(',')})
             AND c.shared = 1 LIMIT 1`,
          model.id,
          ...allowedChannelIds
        );
        if (channelModel) {
          ownerChannelId = channelModel.channelId;
          ownerChannelUserId = channelModel.channelUserId;
        }
      }
    } else {
      const channelModel = await db.get(
        `SELECT c.id as channelId, c.userId as channelUserId, c.shared as channelShared
         FROM Channel c
                JOIN ChannelAllowedModel cam ON c.id = cam.channelId
         WHERE cam.modelId = ?
           AND c.shared = 1 LIMIT 1`,
        model.id
      );
      if (channelModel) {
        ownerChannelId = channelModel.channelId;
        ownerChannelUserId = channelModel.channelUserId;
      }
    }

    // Handle cost deduction
    if (totalCost > 0) {
      console.log('[LOG] Cost calculation:', {tokens: totalTokens, cost: totalCost});
      const currentUser = await db.get('SELECT balance FROM User WHERE id = ?', apiKeyData.userId);
      if (!currentUser) {
        console.warn('[LOG] User not found for balance check:', apiKeyData.userId);
      } else if (currentUser.balance < totalCost) {
        console.warn('[LOG] User has insufficient balance:', {userId: apiKeyData.userId, balance: currentUser.balance, cost: totalCost});
      } else {
        // Check if we should deduct from current user or from channel owner
        let shouldDeductFromCurrentUser = true;
        if (ownerChannelUserId && ownerChannelUserId !== apiKeyData.userId) {
          shouldDeductFromCurrentUser = false;
        }

        if (shouldDeductFromCurrentUser) {
          await db.run('UPDATE User SET balance = balance - ? WHERE id = ?', totalCost, apiKeyData.userId);
          console.log('[LOG] Deducted from user:', {userId: apiKeyData.userId, amount: totalCost});
        }

        if (ownerChannelId && ownerChannelUserId && ownerChannelUserId !== apiKeyData.userId) {
          await db.run('UPDATE User SET balance = balance + ? WHERE id = ?', totalCost, ownerChannelUserId);
          console.log('[LOG] Added to channel owner:', {userId: ownerChannelUserId, amount: totalCost});
        }
      }
    }

    // Always insert the log entry
    const result = await db.run(
      'INSERT INTO Log (latency, promptTokens, completionTokens, totalTokens, apiKeyId, modelName, providerName, cost, ownerChannelId, ownerChannelUserId) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
      latency, promptTokens, completionTokens, totalTokens, apiKeyData.id, model.name, selectedRoute.providerName, totalCost, ownerChannelId, ownerChannelUserId
    );
    const logEntryId = result.lastID;
    console.log('[LOG] Successfully inserted log entry:', {logId: logEntryId, tokens: totalTokens, cost: totalCost});

    // Store detailed log if requested
    if (apiKeyData.logDetails) {
      try {
        await db.run(
          'INSERT INTO LogDetail (logId, requestBody, responseBody) VALUES (?, ?, ?)',
          logEntryId, gzipSync(Buffer.from(JSON.stringify(requestBody))), gzipSync(Buffer.from(JSON.stringify(responseData)))
        );
        console.log('[LOG] Stored detailed log for entry:', logEntryId);
      } catch (detailErr) {
        console.error('[LOG] Failed to store log details:', detailErr);
      }
    }
  } catch (logError) {
    console.error('[LOG] Failed to log request:', logError);
  }
}
