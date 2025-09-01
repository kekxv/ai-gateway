import { NextResponse } from 'next/server';
import { authMiddleware, AuthenticatedRequest } from '@/lib/auth'; // Import authMiddleware
import { getInitializedDb } from '@/lib/db';

// GET /api/providers - Fetches all providers
export const GET = authMiddleware(async (request: AuthenticatedRequest) => {
  try {
    const userId = request.user?.userId;
    const userRole = request.user?.role;

    const db = await getInitializedDb();

    const providers = await db.all(
      `SELECT * FROM Provider ${userRole !== 'ADMIN' ? 'WHERE userId = ?' : ''} ORDER BY createdAt DESC`,
      ...(userRole !== 'ADMIN' ? [userId] : [])
    );

    for (const provider of providers) {
      if (provider.userId) {
        provider.user = await db.get('SELECT id, email, role FROM User WHERE id = ?', provider.userId);
      }
    }
    return NextResponse.json(providers, {
      headers: {
        'Cache-Control': 'no-store, no-cache, must-revalidate, proxy-revalidate',
        'Pragma': 'no-cache',
        'Expires': '0',
      },
    });
  } catch (error) {
    console.error("Error fetching providers:", error);
    return NextResponse.json({ error: '获取提供商失败' }, { status: 500 });
  }
});

// POST /api/providers - Creates a new provider
export const POST = authMiddleware(async (request: AuthenticatedRequest) => {
  try {
    const userId = request.user?.userId; // Get userId from authenticated request
    if (!userId) {
      return NextResponse.json({ error: '未授权: 用户ID缺失' }, { status: 401 });
    }

    const body = await request.json();
    const { name, baseURL, apiKey, type, autoLoadModels } = body;

    if (!name || !baseURL) { // apiKey is now optional
      return NextResponse.json({ error: '缺少必填字段' }, { status: 400 });
    }

    const db = await getInitializedDb();
    const result = await db.run(
      'INSERT INTO Provider (name, baseURL, apiKey, type, autoLoadModels, userId) VALUES (?, ?, ?, ?, ?, ?)',
      name,
      baseURL,
      apiKey,
      type,
      autoLoadModels,
      userId
    );
    const newProvider = await db.get('SELECT * FROM Provider WHERE id = ?', result.lastID);

    return NextResponse.json(newProvider, { status: 201 });
  } catch (error) {
    console.error("Error creating provider:", error);
    if (error instanceof Error && 'code' in error && (error as { code: string }).code === 'P2002') {
      return NextResponse.json({ error: '此名称的提供商已存在' }, { status: 409 });
    }
    return NextResponse.json({ error: '创建提供商失败' }, { status: 500 });
  }
});
