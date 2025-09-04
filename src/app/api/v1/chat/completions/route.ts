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
    const originalRequestedModelName = requestBody.model;
    const streamRequested = requestBody.stream === true;

    if (!originalRequestedModelName) {
      return NextResponse.json({ error: 'Missing \'model\' in request body' }, { status: 400 });
    }

    // 2. Find the Model by its name or alias
    const model = await db.get('SELECT * FROM Model WHERE name = ? OR alias = ?', originalRequestedModelName, originalRequestedModelName);

    if (!model) {
      return NextResponse.json({ error: `Model '${originalRequestedModelName}' not found` }, { status: 404 });
    }

    const upstreamRequestBody = { ...requestBody, model: model.name };
    if (streamRequested) {
      upstreamRequestBody.stream_options = { include_usage: true };
    }

    // 3. Find all eligible ModelRoutes for the requested model, joining with Provider
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

    // 4. Implement weighted random selection to pick a provider
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

    // 6. Forward the request to the upstream provider
    // 6. Billing Check (Initial)
    const user = await db.get('SELECT * FROM User WHERE id = ?', dbKey.userId);
    if (!user) {
      return NextResponse.json({ error: 'User not found for API Key' }, { status: 500 });
    }

    // If model has a cost, check if user has positive balance
    if ((model.inputTokenPrice > 0 || model.outputTokenPrice > 0) && user.balance <= 0) {
      return NextResponse.json({ error: 'Insufficient balance. Please top up your account.' }, { status: 403 });
    }

    const targetUrl = `${selectedRoute.baseURL}/chat/completions`;
    const startTime = Date.now();

    const fetchOptions: RequestInit = {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${selectedRoute.apiKey}`,
      },
      body: JSON.stringify(upstreamRequestBody),
    };

    if (streamRequested) {
      // @ts-expect-error - duplex is required for streaming in Node.js
      fetchOptions.duplex = 'half';
    }

    const upstreamResponse = await fetch(targetUrl, fetchOptions);
    const latency = Date.now() - startTime;

    // 7. Handle response and logging
    if (streamRequested) {
      if (!upstreamResponse.body) {
        return NextResponse.json({ error: "Upstream service returned no response body." }, { status: 502 });
      }

      const [logStream, clientStream] = upstreamResponse.body.tee();

      (async () => {
        let accumulatedContent = '';
        let accumulatedToolCalls: any[] = []; // To store tool calls
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
            // Check if the chunk contains an error
            if (chunk.includes('"error"')) {
              // This might be an error message from the upstream service
              const lines = chunk.split('\n').filter(line => line.startsWith('data: '));
              for (const line of lines) {
                const jsonStr = line.substring(6);
                if (jsonStr.trim() === '[DONE]') continue;
                try {
                  const jsonObj = JSON.parse(jsonStr);
                  if (jsonObj.error) {
                    console.error("Upstream service error in stream:", jsonObj.error);
                    // We'll continue processing for logging purposes, but the client will see the error
                  }
                } catch (e) {}
              }
            }

            const lines = chunk.split('\n').filter(line => line.startsWith('data: '));

            for (const line of lines) {
              const jsonStr = line.substring(6);
              if (jsonStr.trim() === '[DONE]') continue;
              try {
                const jsonObj = JSON.parse(jsonStr);
                if (jsonObj.choices && jsonObj.choices[0] && jsonObj.choices[0].delta) {
                  const delta = jsonObj.choices[0].delta;
                  
                  // Accumulate content
                  if (delta.content) {
                    accumulatedContent += delta.content;
                  }
                  
                  // Accumulate tool calls
                  if (delta.tool_calls) {
                    delta.tool_calls.forEach((toolCall: any) => {
                      if (toolCall.index !== undefined) {
                        // Initialize tool call array if needed
                        if (!accumulatedToolCalls[toolCall.index]) {
                          accumulatedToolCalls[toolCall.index] = {
                            id: toolCall.id || '',
                            type: toolCall.type || 'function',
                            function: { name: '', arguments: '' }
                          };
                        }
                        
                        // Update tool call with new data
                        if (toolCall.id) {
                          accumulatedToolCalls[toolCall.index].id = toolCall.id;
                        }
                        
                        if (toolCall.type) {
                          accumulatedToolCalls[toolCall.index].type = toolCall.type;
                        }
                        
                        if (toolCall.function) {
                          if (toolCall.function.name) {
                            accumulatedToolCalls[toolCall.index].function.name = toolCall.function.name;
                          }
                          if (toolCall.function.arguments) {
                            accumulatedToolCalls[toolCall.index].function.arguments += toolCall.function.arguments;
                          }
                        }
                      }
                    });
                  }
                }
                if (jsonObj.usage) {
                  promptTokens = jsonObj.usage.prompt_tokens || 0;
                  completionTokens = jsonObj.usage.completion_tokens || 0;
                  totalTokens = jsonObj.usage.total_tokens || 0;
                }
              } catch (e) {}
            }
          }

          // Prepare the message object with either content or tool_calls
          const message: any = { role: 'assistant' };
          if (accumulatedToolCalls.length > 0) {
            // If we have tool calls, include them (and remove any empty ones)
            message.tool_calls = accumulatedToolCalls.filter(tc => tc !== undefined);
          } else {
            // Otherwise, just include the content
            message.content = accumulatedContent;
          }

          const formattedResponse = {
            id: 'log-' + Date.now(),
            object: 'chat.completion',
            created: Math.floor(Date.now() / 1000),
            model: requestBody.model,
            choices: [{ index: 0, message, finish_reason: 'stop' }],
            usage: { prompt_tokens: promptTokens, completion_tokens: completionTokens, total_tokens: totalTokens }
          };

          // Calculate cost
          const totalCost = Math.round(((promptTokens / 1000) * model.inputTokenPrice + (completionTokens / 1000) * model.outputTokenPrice)); // Round to nearest integer (cents)

          // Initialize channel owner variables
          let ownerChannelId = null;
          let ownerChannelUserId = null;

          // Only check balance and deduct if cost is greater than 0
          if (totalCost > 0) {
            // Fetch user again to get latest balance (important for concurrency)
            const currentUser = await db.get('SELECT balance FROM User WHERE id = ?', dbKey.userId); // Use dbKey.userId
            if (!currentUser || currentUser.balance < totalCost) {
              // This scenario means user overspent or balance changed during request.
              // For now, we'll just log an error and not deduct.
              // A more robust solution might involve rolling back the request or marking user as negative.
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
            latency, promptTokens, completionTokens, totalTokens, dbKey.id, model.name, selectedRoute.providerName, totalCost, ownerChannelId, ownerChannelUserId
          );
          const logEntryId = result.lastID;

          await db.run(
            'INSERT INTO LogDetail (logId, requestBody, responseBody) VALUES (?, ?, ?)',
            logEntryId, JSON.stringify(requestBody), JSON.stringify(formattedResponse)
          );
        } catch (logError) {
          console.error("Failed to log streaming request:", logError);
        }
      })();

      return new Response(clientStream, {
        headers: { 'Content-Type': upstreamResponse.headers.get('Content-Type') || 'text/plain' },
        status: upstreamResponse.status,
      });
    } else {
      if (!upstreamResponse.ok) {
        const errorText = await upstreamResponse.text();
        let errorMessage = "Upstream service error: Provider returned error";
        
        try {
          const errorData = JSON.parse(errorText);
          if (errorData.error && errorData.error.message) {
            errorMessage = `Upstream service error: ${errorData.error.message}`;
          }
        } catch (e) {
          // If parsing fails, use the raw text if it's not empty
          if (errorText.trim()) {
            errorMessage = `Upstream service error: ${errorText}`;
          }
        }
        
        return NextResponse.json({ error: errorMessage }, { status: upstreamResponse.status });
      }
      const responseData = await upstreamResponse.json();

      if (responseData.usage) {
        try {
          // Calculate cost
          const totalCost = Math.round(((responseData.usage.prompt_tokens / 1000) * model.inputTokenPrice + (responseData.usage.completion_tokens / 1000) * model.outputTokenPrice)); // Round to nearest integer (cents)

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
            latency, responseData.usage.prompt_tokens, responseData.usage.completion_tokens, responseData.usage.total_tokens, dbKey.id, model.name, selectedRoute.providerName, totalCost, ownerChannelId, ownerChannelUserId
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
    }

  } catch (error) {
    console.error("Gateway Error:", error);
    return NextResponse.json({ error: 'An internal server error occurred.' }, { status: 500 });
  }
}
