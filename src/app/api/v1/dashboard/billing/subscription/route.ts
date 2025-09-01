import { NextResponse } from 'next/server';
import { getInitializedDb } from '@/lib/db';

export async function GET(request: Request) {
  try {
    // 1. Authenticate the request using API key
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

    // Get user info associated with this API key
    const user = await db.get(
      'SELECT id, email, role, balance, createdAt, validUntil FROM User WHERE id = ?',
      dbKey.userId
    );

    if (!user) {
      return NextResponse.json({ error: 'User not found' }, { status: 404 });
    }

    // In a real implementation, you might have a separate subscription table
    // For now, we'll return user info with a default subscription plan
    const subscriptionInfo = {
      userId: user.id,
      email: user.email,
      plan: 'free', // Default plan
      status: user.validUntil && new Date() > new Date(user.validUntil) ? 'expired' : 'active',
      currentPeriodEnd: user.validUntil ? new Date(user.validUntil).toISOString() : null,
      balance: user.balance ? user.balance / 10000 : 0, // Convert from internal unit to display unit
      createdAt: user.createdAt,
    };

    return NextResponse.json(subscriptionInfo);
  } catch (error) {
    console.error('Failed to get subscription info:', error);
    return NextResponse.json({ error: 'Internal Server Error' }, { status: 500 });
  }
}