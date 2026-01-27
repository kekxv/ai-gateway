import {NextResponse} from 'next/server';
import {getInitializedDb} from '@/lib/db';
import {withProxySupport} from '@/lib/proxyUtils';
import {createTimeoutSignal, getTimeoutForRequestType} from '@/lib/timeoutConfig';
import {
  authenticateRequest,
  findModelById,
  checkApiKeyPermission,
  findRouteForModelPattern,
  logErrorRequest,
} from '../../_lib/gateway-helpers';

export async function GET(
  request: Request,
  {params}: {params: Promise<{id: string}>}
) {
  try {
    const db = await getInitializedDb();
    const {id: responseId} = await params;

    // 1. Authenticate the request
    const {apiKeyData: dbKey, errorResponse} = await authenticateRequest(request as any, db);
    if (errorResponse) {
      return errorResponse;
    }

    // 2. Get an available route
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

    // 4. Make the upstream request
    const targetUrl = `${selectedRoute.baseURL}/responses/${encodeURIComponent(responseId)}`;
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
      await logErrorRequest(db, dbKey, model, selectedRoute, 0, upstreamResponse.status, `Get response error: ${upstreamResponse.statusText}`);
      return NextResponse.json(errorData, {status: upstreamResponse.status});
    }

    const responseData = await upstreamResponse.json();
    return NextResponse.json(responseData);

  } catch (error) {
    console.error('[RESPONSE] Gateway Error:', error);
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
            await logErrorRequest(db, dbKey, model, selectedRoute, 0, 504, 'Get response timeout');
          } else {
            await logErrorRequest(db, dbKey, model, selectedRoute, 0, 500, errorMessage);
          }
        }
      }
    } catch (logErr) {
      console.error('[LOG] Failed to log get response error:', logErr);
    }
    return NextResponse.json({error: 'An internal server error occurred.'}, {status: 500});
  }
}

export async function DELETE(
  request: Request,
  {params}: {params: Promise<{id: string}>}
) {
  try {
    const db = await getInitializedDb();
    const {id: responseId} = await params;

    // 1. Authenticate the request
    const {apiKeyData: dbKey, errorResponse} = await authenticateRequest(request as any, db);
    if (errorResponse) {
      return errorResponse;
    }

    // 2. Get an available route
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

    // 4. Make the upstream request
    const targetUrl = `${selectedRoute.baseURL}/responses/${encodeURIComponent(responseId)}`;
    const timeoutMs = getTimeoutForRequestType('response');
    const signal = createTimeoutSignal(timeoutMs);

    const upstreamResponse = await fetch(targetUrl, withProxySupport(targetUrl, {
      method: 'DELETE',
      headers: {
        'Authorization': `Bearer ${selectedRoute.apiKey}`,
        'User-Agent': 'AI-Gateway/1.0',
      },
      signal,
    }));

    if (!upstreamResponse.ok) {
      console.error('[RESPONSE] Upstream error:', upstreamResponse.status, upstreamResponse.statusText);
      const errorData = await upstreamResponse.json().catch(() => ({error: 'Upstream error'}));
      await logErrorRequest(db, dbKey, model, selectedRoute, 0, upstreamResponse.status, `Delete response error: ${upstreamResponse.statusText}`);
      return NextResponse.json(errorData, {status: upstreamResponse.status});
    }

    const responseData = await upstreamResponse.json();
    return NextResponse.json(responseData);

  } catch (error) {
    console.error('[RESPONSE] Gateway Error:', error);
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
            await logErrorRequest(db, dbKey, model, selectedRoute, 0, 504, 'Delete response timeout');
          } else {
            await logErrorRequest(db, dbKey, model, selectedRoute, 0, 500, errorMessage);
          }
        }
      }
    } catch (logErr) {
      console.error('[LOG] Failed to log delete response error:', logErr);
    }
    return NextResponse.json({error: 'An internal server error occurred.'}, {status: 500});
  }
}
