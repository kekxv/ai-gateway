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
  const authHeader = request.headers.get('Authorization');
  if (!authHeader || !authHeader.startsWith('Bearer ')) {
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
    return {
      apiKeyData: null,
      errorResponse: NextResponse.json({error: 'Unauthorized: Invalid API Key'}, {status: 401}),
    };
  }

  // Non-blocking update of lastUsed time
  db.run('UPDATE GatewayApiKey SET lastUsed = ? WHERE id = ?', new Date().toISOString(), apiKeyData.id).catch(
    console.error
  );

  return {apiKeyData, errorResponse: null};
}

/**
 * Finds a model by its name or alias.
 * If the model name does not contain a ':', it prefers a version with the ':latest' tag.
 * @param modelName - The name or alias of the model.
 * @param db - The database instance.
 * @returns The model data or null if not found.
 */
export async function findModel(modelName: string, db: Database): Promise<any> {
  if (modelName.includes(':')) {
    return db.get('SELECT * FROM Model WHERE (name = ? OR alias = ?) AND disabled = FALSE', modelName, modelName);
  }

  const modelNameWithLatest = `${modelName}:latest`;
  return db.get(
    `SELECT * FROM Model
     WHERE ((name = ? OR alias = ?) OR (name = ? OR alias = ?)) AND disabled = FALSE
     ORDER BY INSTR(name, ':') DESC, name DESC`,
    modelName,
    modelName,
    modelNameWithLatest,
    modelNameWithLatest
  );
}

/**
 * Selects an upstream route for a given model using weighted random selection.
 * @param modelId - The ID of the model.
 * @param db - The database instance.
 * @returns The selected route data or null if no routes are available.
 */
export async function selectUpstreamRoute(modelId: number, db: Database): Promise<any> {
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
  if (apiKeyData.bindToAllChannels) {
    return null; // Key is bound to all channels, so permission is granted.
  }

  const apiKeyChannels = await db.all(
    'SELECT channelId FROM GatewayApiKeyChannel WHERE apiKeyId = ?',
    apiKeyData.id
  );
  const allowedChannelIds = apiKeyChannels.map((gac: any) => gac.channelId);

  if (allowedChannelIds.length === 0) {
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
    return NextResponse.json(
      {error: `Unauthorized: API Key does not have permission for the requested model.`},
      {status: 403}
    );
  }

  return null; // Permission granted
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
  const user = await db.get('SELECT * FROM User WHERE id = ?', apiKeyData.userId);
  if (!user) {
    // This should ideally not happen if data integrity is maintained.
    return NextResponse.json({error: 'User not found for API Key'}, {status: 500});
  }

  // If model has a cost, check if user has a positive balance.
  if ((modelData.inputTokenPrice > 0 || modelData.outputTokenPrice > 0) && user.balance <= 0) {
    return NextResponse.json({error: 'Insufficient balance. Please top up your account.'}, {status: 403});
  }

  return null; // Balance is sufficient
}

async function shouldDisableRoute(db: Database, selectedRoute: any): Promise<boolean> {
  // 1. Count total enabled models
  const totalModelsResult = await db.get("SELECT COUNT(*) as count FROM Model WHERE disabled = FALSE");
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

  const upstreamResponse = await fetch(targetUrl, fetchOptions);
  const latency = Date.now() - startTime;

  if (streamRequested) {
    if (!upstreamResponse.body) {
      return NextResponse.json({error: "Upstream service returned no response body."}, {status: 502});
    }
    // Placeholder for streaming logic
    return new NextResponse(upstreamResponse.body, {
      headers: {'Content-Type': upstreamResponse.headers.get('Content-Type') || 'text/plain'},
      status: upstreamResponse.status,
    });
  } else {
    if (!upstreamResponse.ok) {
      if (errorCodesToDisable.includes(upstreamResponse.status)) {
        if (await shouldDisableRoute(db, selectedRoute)) {
          const tenMinutesLater = new Date(Date.now() + 10 * 60 * 1000).toISOString();
          db.run('UPDATE ModelRoute SET disabledUntil = ? WHERE id = ?', tenMinutesLater, selectedRoute.id).catch(
            console.error
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
          errorMessage = `Upstream service error: ${errorText}`;
        }
      }
      return NextResponse.json({error: errorMessage}, {status: upstreamResponse.status});
    }
    const responseData = await upstreamResponse.json();
    await logRequestAndCalculateCost(db, apiKeyData, model, selectedRoute, requestBody, responseData, latency, false);
    return NextResponse.json(responseData);
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

  if (!upstreamResponse.ok) {
    if (errorCodesToDisable.includes(upstreamResponse.status)) {
      if (await shouldDisableRoute(db, selectedRoute)) {
        const tenMinutesLater = new Date(Date.now() + 10 * 60 * 1000).toISOString();
        db.run('UPDATE ModelRoute SET disabledUntil = ? WHERE id = ?', tenMinutesLater, selectedRoute.id).catch(
          console.error
        );
      }
    }

    const errorData = await upstreamResponse.json();
    return NextResponse.json({error: `Upstream service error: ${errorData.error?.message || upstreamResponse.statusText}`}, {status: upstreamResponse.status});
  }
  const responseData = await upstreamResponse.json();

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
  try {
    let promptTokens = 0;
    let completionTokens = 0;
    let totalTokens = 0;

    if (streamed) {
      // Logic to parse streaming response and get usage will be complex.
      // For now, let's assume we get it from somewhere.
    } else {
      if (responseData.usage) {
        promptTokens = responseData.usage.prompt_tokens || 0;
        completionTokens = responseData.usage.completion_tokens || 0;
        totalTokens = responseData.usage.total_tokens || 0;
      }
    }

    const totalCost = Math.round(((promptTokens / 1000) * model.inputTokenPrice + (completionTokens / 1000) * model.outputTokenPrice));

    let ownerChannelId = null;
    let ownerChannelUserId = null;

    if (totalCost > 0) {
      const currentUser = await db.get('SELECT balance FROM User WHERE id = ?', apiKeyData.userId);
      if (!currentUser || currentUser.balance < totalCost) {
        console.error(`User ${apiKeyData.userId} has insufficient balance (${currentUser?.balance}) for cost ${totalCost}.`);
      } else {
        let shouldDeduct = true;
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
              if (ownerChannelUserId === apiKeyData.userId) {
                shouldDeduct = false;
              }
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
            if (ownerChannelUserId === apiKeyData.userId) {
              shouldDeduct = false;
            }
          }
        }

        if (shouldDeduct) {
          await db.run('UPDATE User SET balance = balance - ? WHERE id = ?', totalCost, apiKeyData.userId);
        }

        if (ownerChannelId && ownerChannelUserId && ownerChannelUserId !== apiKeyData.userId) {
          await db.run('UPDATE User SET balance = balance + ? WHERE id = ?', totalCost, ownerChannelUserId);
        }
      }
    }

    const result = await db.run(
      'INSERT INTO Log (latency, promptTokens, completionTokens, totalTokens, apiKeyId, modelName, providerName, cost, ownerChannelId, ownerChannelUserId) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
      latency, promptTokens, completionTokens, totalTokens, apiKeyData.id, model.name, selectedRoute.providerName, totalCost, ownerChannelId, ownerChannelUserId
    );
    const logEntryId = result.lastID;

    if (apiKeyData.logDetails) {
      await db.run(
        'INSERT INTO LogDetail (logId, requestBody, responseBody) VALUES (?, ?, ?)',
        logEntryId, gzipSync(Buffer.from(JSON.stringify(requestBody))), gzipSync(Buffer.from(JSON.stringify(responseData)))
      );
    }
  } catch (logError) {
    console.error("Failed to log request:", logError);
  }
}
