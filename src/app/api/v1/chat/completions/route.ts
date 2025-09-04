import {NextResponse} from 'next/server';
import {getInitializedDb} from '@/lib/db';
import {
  authenticateRequest,
  findModel,
  selectUpstreamRoute,
  checkApiKeyPermission,
  checkInitialBalance,
  handleUpstreamRequest
} from '../../_lib/gateway-helpers';

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
    const streamRequested = requestBody.stream === true;

    if (!originalRequestedModelName) {
      return NextResponse.json({error: 'Missing \'model\' in request body'}, {status: 400});
    }

    // 2. Find the Model by its name or alias
    const model = await findModel(originalRequestedModelName, db);

    if (!model) {
      return NextResponse.json({error: `Model '${originalRequestedModelName}' not found`}, {status: 404});
    }

    const upstreamRequestBody = {...requestBody, model: model.name};
    if (streamRequested) {
      upstreamRequestBody.stream_options = {include_usage: true};
    }

    // 3. Select an upstream provider
    const selectedRoute = await selectUpstreamRoute(model.id, db);

    if (!selectedRoute) {
      return NextResponse.json({error: `No enabled routes configured for model '${originalRequestedModelName}'`}, {status: 404});
    }

    // 5. API Key Permission Check
    const permissionError = await checkApiKeyPermission(dbKey, model.id, db);
    if (permissionError) {
      return permissionError;
    }

    // 6. Billing Check (Initial)
    const balanceError = await checkInitialBalance(dbKey, model, db);
    if (balanceError) {
      return balanceError;
    }


    const targetUrl = `${selectedRoute.baseURL}/chat/completions`;

    return handleUpstreamRequest(db, dbKey, model, selectedRoute, upstreamRequestBody, targetUrl, streamRequested);

  } catch (error) {
    console.error("Gateway Error:", error);
    return NextResponse.json({error: 'An internal server error occurred.'}, {status: 500});
  }
}
