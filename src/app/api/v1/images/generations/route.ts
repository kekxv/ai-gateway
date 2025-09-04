import {NextResponse} from 'next/server';
import {getInitializedDb} from '@/lib/db';
import {
  authenticateRequest,
  checkApiKeyPermission,
  checkInitialBalance,
  handleUpstreamRequest,
  findRouteForModelPattern,
  findModel
} from '../../_lib/gateway-helpers';

export async function POST(request: Request) {
  try {
    const db = await getInitializedDb();

    const {apiKeyData: dbKey, errorResponse: authError} = await authenticateRequest(request as any, db);
    if (authError) return authError;

    const requestBody = await request.json();

    const selectedRoute = await findRouteForModelPattern('%dall-e%', db);
    if (!selectedRoute) {
      return NextResponse.json({error: `No enabled routes configured for any DALL-E model`}, {status: 404});
    }

    const model = await findModel(selectedRoute.modelId, db);
    if (!model) {
      return NextResponse.json({error: 'Model not found for selected route'}, {status: 500});
    }

    const permissionError = await checkApiKeyPermission(dbKey, model.id, db);
    if (permissionError) return permissionError;

    const balanceError = await checkInitialBalance(dbKey, model, db);
    if (balanceError) return balanceError;

    const targetUrl = `${selectedRoute.baseURL}/images/generations`;

    return handleUpstreamRequest(db, dbKey, model, selectedRoute, requestBody, targetUrl, false);

  } catch (error) {
    console.error("Gateway Error:", error);
    return NextResponse.json({error: 'An internal server error occurred.'}, {status: 500});
  }
}
