import { NextResponse } from 'next/server';

import bcrypt from 'bcryptjs';
import jwt from 'jsonwebtoken';
import { authenticator } from 'otplib';

import { getInitializedDb } from '@/lib/db';
import { getJwtSecret } from '@/lib/settings';

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const { email, password, totpToken } = body;

    if (!email || !password) {
      return NextResponse.json({ error: '缺少电子邮件或密码' }, { status: 400 });
    }

    const db = await getInitializedDb();

    if (email === 'root') {
      const userCountResult = await db.get('SELECT COUNT(*) as count FROM User');
      const userCount = userCountResult.count;
      if (userCount === 0) {
        // No users exist, proceed to create root user
        const hashedPassword = await bcrypt.hash(password, 10); // Hash the password
        try {
          await db.run(
            'INSERT INTO User (email, password, role) VALUES (?, ?, ?)',
            'root',
            hashedPassword,
            'ADMIN'
          );
          console.log('Initial root user created successfully.');
        } catch (createError) {
          console.error('Error creating initial root user:', createError);
          return NextResponse.json({ error: '创建初始root用户失败' }, { status: 500 });
        }
      }
    }

    // Find user by email
    const user = await db.get('SELECT * FROM User WHERE email = ?', email);
    if (!user) {
      return NextResponse.json({ error: '无效的凭据' }, { status: 401 });
    }

    // Compare passwords
    const isPasswordValid = await bcrypt.compare(password, user.password);
    if (!isPasswordValid) {
      return NextResponse.json({ error: '无效的凭据' }, { status: 401 });
    }

    // Check if user is disabled or expired
    if (user.disabled) {
      return NextResponse.json({ error: '用户已被禁用' }, { status: 401 });
    }
    if (user.validUntil && new Date() > user.validUntil) {
      return NextResponse.json({ error: '用户已过期' }, { status: 401 });
    }

    // If TOTP is enabled, verify the token
    if (user.totpEnabled) {
      if (!totpToken) {
        return NextResponse.json({ error: '需要TOTP令牌' }, { status: 401 });
      }
      if (!user.totpSecret) {
        // This should not happen if totpEnabled is true, but as a safeguard
        console.error(`用户 ${user.id} 启用了TOTP但没有密钥`);
        return NextResponse.json({ error: 'TOTP配置错误，请联系管理员' }, { status: 500 });
      }
      const isTotpValid = authenticator.check(totpToken, user.totpSecret);
      if (!isTotpValid) {
        return NextResponse.json({ error: '无效的TOTP令牌' }, { status: 401 });
      }
    }

    // Generate JWT token
    const jwtSecret = await getJwtSecret();
    const token = jwt.sign(
      { userId: user.id, email: user.email, role: user.role },
      jwtSecret,
      { expiresIn: '8h' } // More user-friendly expiration
    );

    return NextResponse.json({ message: '登录成功', token, role: user.role }, { status: 200 });
  } catch (error) {
    console.error("登录错误:", error);
    return NextResponse.json({ error: '登录失败' }, { status: 500 });
  }
}
