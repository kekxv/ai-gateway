import {NextResponse} from 'next/server';
import {getInitializedDb} from '@/lib/db';
import {
  authenticateRequest,
  findModel,
  selectUpstreamRoute,
  checkApiKeyPermission,
  checkInitialBalance,
  handleUpstreamFormRequest
} from '../../_lib/gateway-helpers';

export async function POST(request: Request) {
  try {
    const db = await getInitializedDb();

    const {apiKeyData: dbKey, errorResponse: authError} = await authenticateRequest(request as any, db);
    if (authError) return authError;

    const formData = await request.formData();
    const modelName = formData.get('model') as string;

    if (!modelName) {
      return NextResponse.json({error: "Missing 'model' in request body"}, {status: 400});
    }

    const model = await findModel(modelName, db);
    if (!model) {
      return NextResponse.json({error: `Model '${modelName}' not found`}, {status: 404});
    }

    const selectedRoute = await selectUpstreamRoute(model.id, db);
    if (!selectedRoute) {
      return NextResponse.json({error: `No enabled routes configured for model '${modelName}'`}, {status: 404});
    }

    const permissionError = await checkApiKeyPermission(dbKey, model.id, db);
    if (permissionError) return permissionError;

    const balanceError = await checkInitialBalance(dbKey, model, db);
    if (balanceError) return balanceError;

    const targetUrl = `${selectedRoute.baseURL}/audio/transcriptions`;

    return handleUpstreamFormRequest(db, dbKey, model, selectedRoute, formData, targetUrl);

  } catch (error) {
    console.error("Gateway Error:", error);
    return NextResponse.json({error: 'An internal server error occurred.'}, {status: 500});
  }
}
