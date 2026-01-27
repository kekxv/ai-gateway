import {NextResponse} from 'next/server';
import {getInitializedDb} from '@/lib/db';
import {
  authenticateRequest,
  findModelById,
  checkApiKeyPermission,
  findRouteForModelPattern
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

    const upstreamResponse = await fetch(targetUrl, {
      method: 'GET',
      headers: {
        'Authorization': `Bearer ${selectedRoute.apiKey}`,
        'User-Agent': 'AI-Gateway/1.0',
      },
    });

    if (!upstreamResponse.ok) {
      console.error('[RESPONSE] Upstream error:', upstreamResponse.status, upstreamResponse.statusText);
      const errorData = await upstreamResponse.json().catch(() => ({error: 'Upstream error'}));
      return NextResponse.json(errorData, {status: upstreamResponse.status});
    }

    const responseData = await upstreamResponse.json();
    return NextResponse.json(responseData);

  } catch (error) {
    console.error('[RESPONSE] Gateway Error:', error);
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

    const upstreamResponse = await fetch(targetUrl, {
      method: 'DELETE',
      headers: {
        'Authorization': `Bearer ${selectedRoute.apiKey}`,
        'User-Agent': 'AI-Gateway/1.0',
      },
    });

    if (!upstreamResponse.ok) {
      console.error('[RESPONSE] Upstream error:', upstreamResponse.status, upstreamResponse.statusText);
      const errorData = await upstreamResponse.json().catch(() => ({error: 'Upstream error'}));
      return NextResponse.json(errorData, {status: upstreamResponse.status});
    }

    const responseData = await upstreamResponse.json();
    return NextResponse.json(responseData);

  } catch (error) {
    console.error('[RESPONSE] Gateway Error:', error);
    return NextResponse.json({error: 'An internal server error occurred.'}, {status: 500});
  }
}
