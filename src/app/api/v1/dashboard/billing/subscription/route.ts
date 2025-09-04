import {NextResponse} from 'next/server';
import {getInitializedDb} from '@/lib/db';
import {authenticateRequest} from '../../../_lib/gateway-helpers';

export async function GET(request: Request) {
  try {
    const db = await getInitializedDb();

    const {apiKeyData: dbKey, errorResponse: authError} = await authenticateRequest(request as any, db);
    if (authError) return authError;

    // Get user info associated with this API key
    const user = await db.get(
      'SELECT id, email, role, balance, createdAt, validUntil FROM User WHERE id = ?',
      dbKey.userId
    );

    if (!user) {
      return NextResponse.json({error: 'User not found'}, {status: 404});
    }

    // In a real implementation, you might have a separate subscription table
    // For now, we'll return user info with a default subscription plan
    const subscriptionInfo = {
      userId: user.id,
      email: user.email,
      plan: 'free', // Default plan
      status: user.validUntil && new Date() > new Date(user.validUntil) ? 'expired' : 'active',
      currentPeriodEnd: user.validUntil ? new Date(user.validUntil).toISOString() : null,
      balance: user.balance !== undefined && user.balance !== null ? user.balance / 10000 : 0, // Convert from internal unit to display unit
      createdAt: user.createdAt,
    };

    return NextResponse.json(subscriptionInfo);
  } catch (error) {
    console.error('Failed to get subscription info:', error);
    return NextResponse.json({error: 'Internal Server Error'}, {status: 500});
  }
}
