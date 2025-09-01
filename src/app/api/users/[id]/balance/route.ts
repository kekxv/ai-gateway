import { NextResponse } from 'next/server';
import { authMiddleware, AuthenticatedRequest } from '@/lib/auth';
import { getInitializedDb } from '@/lib/db';

export const PUT = authMiddleware(async (request: AuthenticatedRequest, context: { params: Promise<{ id: string }> }) => {
  try {
    const { id } = await context.params;
    const userRole = request.user?.role;

    if (userRole !== 'ADMIN') {
      return NextResponse.json({ error: 'Unauthorized: Only administrators can adjust user balances.' }, { status: 403 });
    }

    if (isNaN(parseInt(id))) {
      return NextResponse.json({ error: 'Invalid user ID.' }, { status: 400 });
    }

    const body = await request.json();
    const { amount } = body;

    if (typeof amount !== 'number') {
      return NextResponse.json({ error: 'Missing or invalid amount.' }, { status: 400 });
    }

    const db = await getInitializedDb();
    const existingUser = await db.get('SELECT * FROM User WHERE id = ?', id);

    if (!existingUser) {
      return NextResponse.json({ error: 'User not found.' }, { status: 404 });
    }

    await db.run('UPDATE User SET balance = ? WHERE id = ?', amount, id);

    const updatedUser = await db.get('SELECT id, email, role, balance FROM User WHERE id = ?', id);

    return NextResponse.json(updatedUser);
  } catch (error) {
    console.error("Error adjusting user balance:", error);
    return NextResponse.json({ error: 'Failed to adjust user balance.' }, { status: 500 });
  }
});
