import { NextResponse } from 'next/server';
import prisma from '@/lib/prisma';

export async function DELETE() {
  try {
    const thirtyDaysAgo = new Date();
    thirtyDaysAgo.setDate(thirtyDaysAgo.getDate() - 30);

    const { count } = await prisma.logDetail.deleteMany({
      where: {
        createdAt: {
          lt: thirtyDaysAgo,
        },
      },
    });

    return NextResponse.json({ message: `Deleted ${count} log details older than 30 days.` });
  } catch (error: any) {
    console.error('Error cleaning up log details:', error);
    return NextResponse.json({ message: 'Error cleaning up log details.', error: error.message }, { status: 500 });
  }
}
