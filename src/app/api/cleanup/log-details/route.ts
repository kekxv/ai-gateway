import { NextResponse } from 'next/server';
import { authMiddleware, AuthenticatedRequest } from '@/lib/auth';
import { getInitializedDb } from '@/lib/db';

export const POST = authMiddleware(async (request: AuthenticatedRequest) => {
  try {
    const userRole = request.user?.role;

    if (userRole !== 'ADMIN') {
      return NextResponse.json({ error: 'Unauthorized: Only administrators can perform this action.' }, { status: 403 });
    }

    const db = await getInitializedDb();

    const thirtyDaysAgo = new Date();
    thirtyDaysAgo.setDate(thirtyDaysAgo.getDate() - 30);

    const result = await db.run(
      'DELETE FROM LogDetail WHERE createdAt < ?',
      thirtyDaysAgo.toISOString()
    );

    return NextResponse.json({ message: `Successfully deleted ${result.changes} log details older than 30 days.` });
  } catch (error) {
    console.error("Error deleting old log details:", error);
    return NextResponse.json({ error: 'An internal server error occurred during cleanup.' }, { status: 500 });
  }
});