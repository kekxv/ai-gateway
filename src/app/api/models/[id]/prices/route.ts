import { NextResponse } from 'next/server';
import { authMiddleware, AuthenticatedRequest } from '@/lib/auth';
import { getInitializedDb } from '@/lib/db';

export const PUT = authMiddleware(async (request: AuthenticatedRequest, context: { params: Promise<{ id: string }> }) => {
  try {
    const { id } = await context.params;
    const userRole = request.user?.role;

    if (userRole !== 'ADMIN') {
      return NextResponse.json({ error: 'Unauthorized: Only administrators can set model prices.' }, { status: 403 });
    }

    if (isNaN(parseInt(id))) {
      return NextResponse.json({ error: 'Invalid model ID.' }, { status: 400 });
    }

    const body = await request.json();
    const { inputTokenPrice, outputTokenPrice } = body;

    if (typeof inputTokenPrice !== 'number' || typeof outputTokenPrice !== 'number') {
      return NextResponse.json({ error: 'Missing or invalid token prices.' }, { status: 400 });
    }

    const db = await getInitializedDb();
    const existingModel = await db.get('SELECT * FROM Model WHERE id = ?', id);

    if (!existingModel) {
      return NextResponse.json({ error: 'Model not found.' }, { status: 404 });
    }

    await db.run(
      'UPDATE Model SET inputTokenPrice = ?, outputTokenPrice = ? WHERE id = ?',
      inputTokenPrice, outputTokenPrice, id
    );

    const updatedModel = await db.get('SELECT id, name, inputTokenPrice, outputTokenPrice FROM Model WHERE id = ?', id);

    return NextResponse.json(updatedModel);
  } catch (error) {
    console.error("Error setting model prices:", error);
    return NextResponse.json({ error: 'Failed to set model prices.' }, { status: 500 });
  }
});
