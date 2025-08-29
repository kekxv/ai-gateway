import { NextResponse } from 'next/server';
import bcrypt from 'bcryptjs';
import { authMiddleware, AuthenticatedRequest } from '@/lib/auth';
import { getInitializedDb } from '@/lib/db';

// GET /api/users/[id] - 获取单个用户信息
export const GET = authMiddleware(async (request: AuthenticatedRequest, context: { params: Promise<{ id: string }> }) => {
  try {
    // 只有管理员可以获取用户信息
    if (request.user?.role !== 'ADMIN') {
      return NextResponse.json({ error: '未授权: 只有管理员可以访问' }, { status: 403 });
    }

    const params = await context.params;
    const { id } = params;
    const userId = parseInt(id, 10);

    if (isNaN(userId)) {
      return NextResponse.json({ error: '无效的用户 ID' }, { status: 400 });
    }

    const db = await getInitializedDb();
    const user = await db.get(
      'SELECT id, email, role, disabled, validUntil, createdAt FROM User WHERE id = ?',
      userId
    );

    if (!user) {
      return NextResponse.json({ error: '用户未找到' }, { status: 404 });
    }

    return NextResponse.json(user, { status: 200 });
  } catch (error) {
    console.error("获取用户信息错误:", error);
    return NextResponse.json({ error: '获取用户信息失败' }, { status: 500 });
  }
}, ['ADMIN']);

// PUT /api/users/[id] - 更新用户信息
export const PUT = authMiddleware(async (request: AuthenticatedRequest, context: { params: Promise<{ id: string }> }) => {
  try {
    // 只有管理员可以更新用户信息
    if (request.user?.role !== 'ADMIN') {
      return NextResponse.json({ error: '未授权: 只有管理员可以访问' }, { status: 403 });
    }

    const params = await context.params;
    const { id } = params;
    const userId = parseInt(id, 10);

    if (isNaN(userId)) {
      return NextResponse.json({ error: '无效的用户 ID' }, { status: 400 });
    }

    // 检查用户是否存在
    const db = await getInitializedDb();
    const existingUser = await db.get('SELECT * FROM User WHERE id = ?', userId);

    if (!existingUser) {
      return NextResponse.json({ error: '用户未找到' }, { status: 404 });
    }

    const body = await request.json();
    const { email, password, role, disabled, validUntil } = body;

    const updateFields: string[] = [];
    const updateValues: any[] = [];

    if (email && email !== existingUser.email) {
      updateFields.push(`email = ?`);
      updateValues.push(email);
    }
    if (password) {
      updateFields.push(`password = ?`);
      updateValues.push(await bcrypt.hash(password, 10));
    }
    if (role) {
      updateFields.push(`role = ?`);
      updateValues.push(role);
    }
    if (disabled !== undefined) {
      updateFields.push(`disabled = ?`);
      updateValues.push(disabled);
    }
    if (validUntil !== undefined) {
      updateFields.push(`validUntil = ?`);
      updateValues.push(validUntil ? new Date(validUntil).toISOString() : null);
    }

    if (updateFields.length > 0) {
      await db.run(
        `UPDATE User SET ${updateFields.join(', ')} WHERE id = ?`,
        ...updateValues,
        userId
      );
    }

    const user = await db.get(
      'SELECT id, email, role, disabled, validUntil, createdAt FROM User WHERE id = ?',
      userId
    );

    return NextResponse.json(user, { status: 200 });
  } catch (error) {
    console.error("更新用户信息错误:", error);
    return NextResponse.json({ error: '更新用户信息失败' }, { status: 500 });
  }
}, ['ADMIN']);

// DELETE /api/users/[id] - 删除用户
export const DELETE = authMiddleware(async (request: AuthenticatedRequest, context: { params: Promise<{ id: string }> }) => {
  try {
    // 只有管理员可以删除用户
    if (request.user?.role !== 'ADMIN') {
      return NextResponse.json({ error: '未授权: 只有管理员可以访问' }, { status: 403 });
    }

    const params = await context.params;
    const { id } = params;
    const userId = parseInt(id, 10);

    if (isNaN(userId)) {
      return NextResponse.json({ error: '无效的用户 ID' }, { status: 400 });
    }

    // 检查用户是否存在
    const db = await getInitializedDb();
    const existingUser = await db.get('SELECT * FROM User WHERE id = ?', userId);

    if (!existingUser) {
      return NextResponse.json({ error: '用户未找到' }, { status: 404 });
    }

    // 删除用户
    await db.run('DELETE FROM User WHERE id = ?', userId);

    return NextResponse.json({ message: '用户已删除' }, { status: 200 });
  } catch (error) {
    console.error("删除用户错误:", error);
    return NextResponse.json({ error: '删除用户失败' }, { status: 500 });
  }
}, ['ADMIN']);