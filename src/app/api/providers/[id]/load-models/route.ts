import { NextResponse } from 'next/server';
import { authMiddleware, AuthenticatedRequest } from '@/lib/auth';
import { getInitializedDb } from '@/lib/db';

// GET handler to fetch models from a provider
export const GET = authMiddleware(async (request: AuthenticatedRequest, context: { params: Promise<{ id: string }> }) => {
  try {
    const params = await context.params;
    const { id } = params;
    const providerId = parseInt(id, 10);

    if (isNaN(providerId)) {
      return NextResponse.json({ error: '无效的提供商 ID' }, { status: 400 });
    }

    const db = await getInitializedDb();
    const provider = await db.get('SELECT * FROM Provider WHERE id = ?', providerId);

    if (!provider) {
      return NextResponse.json({ error: '提供商未找到' }, { status: 404 });
    }

    let modelsToFetch: { id: string; name: string; description?: string }[] = [];

    // Determine provider type and fetch models accordingly
    if (provider.type?.toLowerCase() === 'openai') {
      const openaiResponse = await fetch(`${provider.baseURL}/models`, {
        headers: {
          'Authorization': `Bearer ${provider.apiKey}`,
        },
      });

      const openaiRawText = await openaiResponse.text();
      if (!openaiResponse.ok) {
        return NextResponse.json({ error: `从 OpenAI 获取模型失败: ${openaiRawText}` }, { status: openaiResponse.status });
      }

      try {
        const openaiData = JSON.parse(openaiRawText);
        modelsToFetch = openaiData.data.map((model: any) => ({
          id: model.id,
          name: model.id,
          description: model.object,
        }));
      } catch (e) {
        return NextResponse.json({ error: '解析 OpenAI 模型数据失败' }, { status: 500 });
      }

    } else if (provider.type?.toLowerCase() === 'gemini') {
      const apiKey = provider.apiKey || '';
      const geminiResponse = await fetch(`${provider.baseURL}/v1beta/models`, {
        headers: {
          'x-goog-api-key': apiKey,
        },
      });

      if (!geminiResponse.ok) {
        const errorText = await geminiResponse.text();
        return NextResponse.json({ error: `从 Gemini 获取模型失败: ${errorText}` }, { status: geminiResponse.status });
      }

      const geminiData = await geminiResponse.json();
      modelsToFetch = geminiData.models.map((model: any) => ({
        id: model.name,
        name: model.displayName || model.name,
        description: model.description,
      }));

    } else {
      return NextResponse.json({ error: '不支持的提供商类型' }, { status: 400 });
    }

    // Return the list of models fetched from the provider
    return NextResponse.json(modelsToFetch, { status: 200 });

  } catch (error) {
    console.error("加载模型列表错误:", error);
    return NextResponse.json({ error: '从提供商加载模型列表失败' }, { status: 500 });
  }
});
