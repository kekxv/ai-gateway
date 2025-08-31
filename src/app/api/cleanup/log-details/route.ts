import { NextResponse } from 'next/server';
import { authMiddleware } from '@/lib/auth'; // Import authMiddleware
import { getInitializedDb } from '@/lib/db';

export const DELETE = authMiddleware(async () => {
  try {
    const thirtyDaysAgo = new Date();
    thirtyDaysAgo.setDate(thirtyDaysAgo.getDate() - 30);

    const db = await getInitializedDb();
    const result = await db.run(
      'DELETE FROM LogDetail WHERE createdAt < ?',
      thirtyDaysAgo.toISOString()
    );
    const count = result.changes;

    return NextResponse.json({ message: `Deleted ${count} log details older than 30 days.` });
  } catch (error: any) {
    console.error('Error cleaning up log details:', error);
    return NextResponse.json({ message: 'Error cleaning up log details.', error: error.message }, { status: 500 });
  }
}, ['ADMIN']);
