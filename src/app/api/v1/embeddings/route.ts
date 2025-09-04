import { NextResponse } from 'next/server';
import { getInitializedDb } from '@/lib/db';
import {
  authenticateRequest,
  findModel,
  selectUpstreamRoute,
  checkApiKeyPermission,
  checkInitialBalance,
  handleUpstreamRequest
} from '../_lib/gateway-helpers';

export async function POST(request: Request) {
  try {
    const db = await getInitializedDb();

    const { apiKeyData: dbKey, errorResponse: authError } = await authenticateRequest(request as any, db);
    if (authError) return authError;

    const requestBody = await request.json();
    const originalRequestedModelName = requestBody.model;

    if (!originalRequestedModelName) {
      return NextResponse.json({ error: "Missing 'model' in request body" }, { status: 400 });
    }

    const model = await findModel(originalRequestedModelName, db);
    if (!model) {
      return NextResponse.json({ error: `Model '${originalRequestedModelName}' not found` }, { status: 404 });
    }

    const upstreamRequestBody = { ...requestBody, model: model.name };

    const selectedRoute = await selectUpstreamRoute(model.id, db);
    if (!selectedRoute) {
      return NextResponse.json({ error: `No enabled routes configured for model '${originalRequestedModelName}'` }, { status: 404 });
    }

    const permissionError = await checkApiKeyPermission(dbKey, model.id, db);
    if (permissionError) return permissionError;

    const balanceError = await checkInitialBalance(dbKey, model, db);
    if (balanceError) return balanceError;

    const targetUrl = `${selectedRoute.baseURL}/embeddings`;

    return handleUpstreamRequest(db, dbKey, model, selectedRoute, upstreamRequestBody, targetUrl, false);

  } catch (error) {
    console.error("Gateway Error:", error);
    return NextResponse.json({ error: 'An internal server error occurred.' }, { status: 500 });
  }
}
