import { NextResponse } from 'next/server';
import { authMiddleware, AuthenticatedRequest } from '@/lib/auth'; // Import authMiddleware
import { getInitializedDb } from '@/lib/db';

// PUT /api/providers/[id] - Updates a provider
export const PUT = authMiddleware(async (request: AuthenticatedRequest, context: { params: { id: string } }) => {
  try {
    const { id: paramId } = await context.params;
    const id = parseInt(paramId);
    const userId = request.user?.userId;
    const userRole = request.user?.role;

    if (isNaN(id)) {
      return NextResponse.json({ error: '缺少必填字段或无效的 ID' }, { status: 400 });
    }

    // Check ownership or admin role
    const db = await getInitializedDb();
    const existingProvider = await db.get('SELECT * FROM Provider WHERE id = ?', id);
    if (!existingProvider) {
      return NextResponse.json({ error: '提供商未找到' }, { status: 404 });
    }
    if (userRole !== 'ADMIN' && existingProvider.userId !== userId) {
      return NextResponse.json({ error: '无权更新此提供商' }, { status: 403 });
    }

    const body = await request.json();
    const { name, baseURL, apiKey, newUserId, type, autoLoadModels } = body; // Added newUserId, type, autoLoadModels

    if (!name || !baseURL) { // apiKey is now optional
      return NextResponse.json({ error: '缺少必填字段' }, { status: 400 });
    }

    // Validate newUserId if provided and user is admin
    if (newUserId !== undefined && userRole !== 'ADMIN') {
      return NextResponse.json({ error: '无权更改提供商所有者' }, { status: 403 });
    }
    if (newUserId !== undefined) {
      const targetUser = await db.get('SELECT * FROM User WHERE id = ?', newUserId);
      if (!targetUser) {
        return NextResponse.json({ error: '目标用户不存在' }, { status: 400 });
      }
    }

    const updateFields: string[] = [`name = ?`, `baseURL = ?`, `apiKey = ?`, `type = ?`, `autoLoadModels = ?`];
    const updateValues: any[] = [name, baseURL, apiKey, type, autoLoadModels];

    if (newUserId !== undefined) {
      updateFields.push(`userId = ?`);
      updateValues.push(newUserId);
    }

    await db.run(
      `UPDATE Provider SET ${updateFields.join(', ')} WHERE id = ?`,
      ...updateValues,
      id
    );

    const updatedProvider = await db.get('SELECT * FROM Provider WHERE id = ?', id);

    return NextResponse.json(updatedProvider);
  } catch (error) {
    console.error("Error updating provider:", error);
    if (error instanceof Error && 'code' in error && (error as { code: string }).code === 'P2002') {
      return NextResponse.json({ error: '此名称的提供商已存在' }, { status: 409 });
    }
    return NextResponse.json({ error: '更新提供商失败' }, { status: 500 });
  }
});

// DELETE /api/providers/[id] - Deletes a provider
export const DELETE = authMiddleware(async (request: AuthenticatedRequest, context: { params: { id: string } }) => {
  try {
    const { id: paramId } = await context.params;
    const id = parseInt(paramId);
    const userId = request.user?.userId;
    const userRole = request.user?.role;

    if (isNaN(id)) {
      return NextResponse.json({ error: '缺少提供商 ID 或无效的 ID' }, { status: 400 });
    }

    // Check ownership or admin role
    const db = await getInitializedDb();
    const existingProvider = await db.get('SELECT * FROM Provider WHERE id = ?', id);
    if (!existingProvider) {
      return NextResponse.json({ error: '提供商未找到' }, { status: 404 });
    }
    if (userRole !== 'ADMIN' && existingProvider.userId !== userId) {
      return NextResponse.json({ error: '无权删除此提供商' }, { status: 403 });
    }

    await db.run('DELETE FROM Provider WHERE id = ?', id);

    return NextResponse.json({ message: '提供商删除成功' });
  } catch (error) {
    console.error("Error deleting provider:", error);
    return NextResponse.json({ error: '删除提供商失败' }, { status: 500 });
  }
});