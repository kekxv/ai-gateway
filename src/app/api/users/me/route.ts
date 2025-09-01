import { NextResponse } from 'next/server';
import { authMiddleware, AuthenticatedRequest } from '@/lib/auth';
import { getInitializedDb } from '@/lib/db';

async function getCurrentUser(req: AuthenticatedRequest) {
  try {
    const userId = req.user?.userId;
    if (!userId) {
      return NextResponse.json({ error: 'User not found in token' }, { status: 400 });
    }

    const db = await getInitializedDb();
    const user = await db.get(
      'SELECT id, email, role, disabled, validUntil, createdAt, totpEnabled, balance FROM User WHERE id = ?',
      userId
    );

    if (!user) {
      return NextResponse.json({ error: 'User not found' }, { status: 404 });
    }

    return NextResponse.json(user);
  } catch (error) {
    console.error('Failed to get current user:', error);
    return NextResponse.json({ error: 'Internal Server Error' }, { status: 500 });
  }
}

export const GET = authMiddleware(getCurrentUser);
