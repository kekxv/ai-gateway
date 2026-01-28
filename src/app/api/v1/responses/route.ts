import {NextResponse} from 'next/server';
import {getInitializedDb} from '@/lib/db';
import {withProxySupport} from '@/lib/proxyUtils';
import {createTimeoutSignal, getTimeoutForRequestType} from '@/lib/timeoutConfig';
import {
  authenticateRequest,
  findModel,
  selectUpstreamRoute,
  checkApiKeyPermission,
  checkInitialBalance,
  handleUpstreamRequest,
  findRouteForModelPattern,
  findModelById,
  logErrorRequest,
} from '../_lib/gateway-helpers';

export async function POST(request: Request) {
  try {
    const db = await getInitializedDb();

    // 1. Authenticate the request
    const {apiKeyData: dbKey, errorResponse} = await authenticateRequest(request as any, db);
    if (errorResponse) {
      return errorResponse;
    }

    const requestBody = await request.json();
    const originalRequestedModelName = requestBody.model;

    if (!originalRequestedModelName) {
      return NextResponse.json({error: 'Missing \'model\' in request body'}, {status: 400});
    }

    // 2. Find the Model by its name or alias
    const model = await findModel(originalRequestedModelName, db);

    if (!model) {
      return NextResponse.json({error: `Model '${originalRequestedModelName}' not found`}, {status: 404});
    }

    // 3. Select an upstream provider
    const selectedRoute = await selectUpstreamRoute(model.id, db);

    if (!selectedRoute) {
      return NextResponse.json({error: `No enabled routes configured for model '${originalRequestedModelName}'`}, {status: 404});
    }

    // 4. API Key Permission Check
    const permissionError = await checkApiKeyPermission(dbKey, model.id, db);
    if (permissionError) {
      return permissionError;
    }

    // 5. Billing Check (Initial)
    const balanceError = await checkInitialBalance(dbKey, model, db);
    if (balanceError) {
      return balanceError;
    }

    const upstreamRequestBody = {...requestBody, model: model.name};
    const targetUrl = `${selectedRoute.baseURL}/responses`;

    return handleUpstreamRequest(db, dbKey, model, selectedRoute, upstreamRequestBody, targetUrl, false);

  } catch (error) {
    console.error('[RESPONSE] Gateway Error:', error);
    return NextResponse.json({error: 'An internal server error occurred.'}, {status: 500});
  }
}

export async function GET(request: Request) {
  try {
    const db = await getInitializedDb();

    // 1. Authenticate the request
    const {apiKeyData: dbKey, errorResponse} = await authenticateRequest(request as any, db);
    if (errorResponse) {
      return errorResponse;
    }

    // Get a generic route for responses (use first available)
    const selectedRoute = await findRouteForModelPattern('%', db);

    if (!selectedRoute) {
      return NextResponse.json({error: 'No enabled routes configured'}, {status: 503});
    }

    const model = await findModelById(selectedRoute.modelId, db);
    if (!model) {
      return NextResponse.json({error: 'Model not found'}, {status: 500});
    }

    // 3. API Key Permission Check
    const permissionError = await checkApiKeyPermission(dbKey, model.id, db);
    if (permissionError) {
      return permissionError;
    }

    // 4. Make the upstream request to list responses
    const targetUrl = `${selectedRoute.baseURL}/responses`;

    const timeoutMs = getTimeoutForRequestType('response');
    const signal = createTimeoutSignal(timeoutMs);

    const upstreamResponse = await fetch(targetUrl, withProxySupport(targetUrl, {
      method: 'GET',
      headers: {
        'Authorization': `Bearer ${selectedRoute.apiKey}`,
        'User-Agent': 'AI-Gateway/1.0',
      },
      signal,
    }));

    if (!upstreamResponse.ok) {
      console.error('[RESPONSE] Upstream error:', upstreamResponse.status, upstreamResponse.statusText);
      const errorData = await upstreamResponse.json().catch(() => ({error: 'Upstream error'}));
      await logErrorRequest(db, dbKey, model, selectedRoute, 0, upstreamResponse.status, `Response list error: ${upstreamResponse.statusText}`, {_method: 'GET'});
      return NextResponse.json(errorData, {status: upstreamResponse.status});
    }

    const responseData = await upstreamResponse.json();
    return NextResponse.json(responseData);

  } catch (error) {
    console.error('[RESPONSE] Gateway Error:', error);
    const latency = 0;
    const errorMessage = error instanceof Error ? error.message : 'An internal server error occurred';
    // Try to log if we have the necessary data
    try {
      const db = await getInitializedDb();
      const {apiKeyData: dbKey} = await authenticateRequest(request as any, db);
      const selectedRoute = await findRouteForModelPattern('%', db);
      if (dbKey && selectedRoute && selectedRoute.modelId) {
        const model = await findModelById(selectedRoute.modelId, db);
        if (model) {
          if (error instanceof Error && error.name === 'AbortError') {
            await logErrorRequest(db, dbKey, model, selectedRoute, latency, 504, 'Response list timeout', {_method: 'GET'});
          } else {
            await logErrorRequest(db, dbKey, model, selectedRoute, latency, 500, errorMessage, {_method: 'GET'});
          }
        }
      }
    } catch (logErr) {
      console.error('[LOG] Failed to log response list error:', logErr);
    }
    return NextResponse.json({error: 'An internal server error occurred.'}, {status: 500});
  }
}
