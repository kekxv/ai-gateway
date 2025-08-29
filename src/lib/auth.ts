import { NextRequest, NextResponse } from 'next/server';
import jwt from 'jsonwebtoken';
import { getInitializedDb } from '@/lib/db';

export interface AuthenticatedRequest extends NextRequest {
  user?: { userId: number; email: string; role: string };
}

// A generic handler type that can represent any Next.js API route handler
type ApiHandler = (req: AuthenticatedRequest, ...args: any[]) => Promise<NextResponse>;

export function authMiddleware(handler: ApiHandler, requiredRoles: string[] = []) {
  return async (req: NextRequest, ...args: any[]) => {
    const authHeader = req.headers.get('Authorization');

    if (!authHeader || !authHeader.startsWith('Bearer ')) {
      return NextResponse.json({ error: '未授权: 缺少或无效的 Authorization 头' }, { status: 401 });
    }

    const token = authHeader.split(' ')[1];

    try {
      const decoded = jwt.verify(token, process.env.JWT_SECRET || 'your_jwt_secret') as { userId: number; email: string; role: string };
      
      const authenticatedRequest = req as AuthenticatedRequest;
      authenticatedRequest.user = decoded;

      const db = await getInitializedDb();
      if (decoded.role !== 'ADMIN') {
        const user = await db.get(
          'SELECT disabled, validUntil FROM User WHERE id = ?',
          decoded.userId
        );

        if (user?.disabled) {
          return NextResponse.json({ error: '未授权: 用户已被禁用' }, { status: 401 });
        }

        if (user?.validUntil && new Date() > user.validUntil) {
          return NextResponse.json({ error: '未授权: 用户已过期' }, { status: 401 });
        }
      }

      if (requiredRoles.length > 0 && !requiredRoles.includes(decoded.role)) {
        return NextResponse.json({ error: '未授权: 没有足够的权限' }, { status: 403 });
      }

      return handler(authenticatedRequest, ...args);
    } catch (error) {
      console.error("认证错误:", error);
      return NextResponse.json({ error: '未授权: 无效的令牌' }, { status: 401 });
    }
  };
}