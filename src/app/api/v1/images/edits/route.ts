import { NextResponse } from 'next/server';
import { getInitializedDb } from '@/lib/db';
import {
  authenticateRequest,
  checkApiKeyPermission,
  checkInitialBalance,
  findRouteForModelPattern,
  findModel,
  handleUpstreamFormRequest
} from '../../_lib/gateway-helpers';

export async function POST(request: Request) {
  try {
    const db = await getInitializedDb();

    const { apiKeyData: dbKey, errorResponse: authError } = await authenticateRequest(request as any, db);
    if (authError) return authError;

    const formData = await request.formData();

    const selectedRoute = await findRouteForModelPattern('%dall-e%', db);
    if (!selectedRoute) {
      return NextResponse.json({ error: `No enabled routes configured for any DALL-E model` }, { status: 404 });
    }

    const model = await findModel(selectedRoute.modelId, db);
    if (!model) {
      return NextResponse.json({ error: 'Model not found for selected route' }, { status: 500 });
    }

    const permissionError = await checkApiKeyPermission(dbKey, model.id, db);
    if (permissionError) return permissionError;

    const balanceError = await checkInitialBalance(dbKey, model, db);
    if (balanceError) return balanceError;

    const targetUrl = `${selectedRoute.baseURL}/images/edits`;

    return handleUpstreamFormRequest(db, dbKey, model, selectedRoute, formData, targetUrl);

  } catch (error) {
    console.error("Gateway Error:", error);
    return NextResponse.json({ error: 'An internal server error occurred.' }, { status: 500 });
  }
}
