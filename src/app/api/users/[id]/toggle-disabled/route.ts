import {NextResponse} from 'next/server';
import {authMiddleware, AuthenticatedRequest} from '@/lib/auth';
import {getInitializedDb} from '@/lib/db';

// POST /api/users/[id]/toggle-disabled - 切换用户禁用状态
export const POST = authMiddleware(async (request: AuthenticatedRequest, context: {
  params: Promise<{ id: string }>
}) => {
  try {
    // 只有管理员可以切换用户禁用状态
    if (request.user?.role !== 'ADMIN') {
      return NextResponse.json({error: '未授权: 只有管理员可以访问'}, {status: 403});
    }

    const params = await context.params;
    const {id} = params;
    const userId = parseInt(id, 10);

    if (isNaN(userId)) {
      return NextResponse.json({error: '无效的用户 ID'}, {status: 400});
    }

    // 检查用户是否存在
    const db = await getInitializedDb();
    const existingUser = await db.get(
      'SELECT id, disabled FROM User WHERE id = ?',
      userId
    );

    if (!existingUser) {
      return NextResponse.json({error: '用户未找到'}, {status: 404});
    }

    // 切换禁用状态
    const updatedUser = await db.run(
      'UPDATE User SET disabled = ? WHERE id = ?',
      !existingUser.disabled,
      userId
    );
    await db.get('SELECT id, email, disabled FROM User WHERE id = ?', userId);
    const action = updatedUser.disabled ? '禁用' : '启用';
    return NextResponse.json({
      message: `用户已${action}`,
      user: updatedUser
    }, {status: 200});
  } catch (error) {
    console.error("切换用户禁用状态错误:", error);
    return NextResponse.json({error: '切换用户禁用状态失败'}, {status: 500});
  }
}, ['ADMIN']);
