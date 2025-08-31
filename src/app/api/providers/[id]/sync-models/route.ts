import { NextResponse } from 'next/server';
import { authMiddleware, AuthenticatedRequest } from '@/lib/auth';
import { getInitializedDb } from '@/lib/db';

export const POST = authMiddleware(async (request: AuthenticatedRequest, context: { params: { id: string } }) => {
  try {
    const { id } = context.params;
    const providerId = parseInt(id, 10);
    const userId = request.user?.userId;
    const userRole = request.user?.role;

    if (isNaN(providerId)) {
      return NextResponse.json({ error: '无效的提供商 ID' }, { status: 400 });
    }

    const db = await getInitializedDb();
    const provider = await db.get('SELECT * FROM Provider WHERE id = ?', providerId);

    if (!provider) {
      return NextResponse.json({ error: '提供商未找到' }, { status: 404 });
    }

    // Check if user has permission (admin or owner)
    if (userRole !== 'ADMIN' && provider.userId !== userId) {
      return NextResponse.json({ error: '无权同步此提供商的模型' }, { status: 403 });
    }

    // Check if autoLoadModels is enabled for this provider
    if (!provider.autoLoadModels) {
      return NextResponse.json({ error: '此提供商未启用自动加载模型' }, { status: 400 });
    }

    let modelsToFetch: { id: string; name: string; description?: string }[] = [];

    // Replicate model fetching logic from load-models/route.ts
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

    // --- Compare and update database ---
    let newModelsCount = 0;
    let updatedProviderModelsCount = 0;

    for (const fetchedModel of modelsToFetch) {
      // Check if Model exists
      let existingModel = await db.get('SELECT * FROM Model WHERE name = ?', fetchedModel.name);

      if (!existingModel) {
        // Create new Model entry if it doesn't exist
        const result = await db.run(
          'INSERT INTO Model (name, description) VALUES (?, ?)',
          fetchedModel.name,
          fetchedModel.description || null
        );
        existingModel = await db.get('SELECT * FROM Model WHERE id = ?', result.lastID);
        newModelsCount++;
      }

      // Check if ProviderModel exists for this provider and model
      const existingProviderModel = await db.get(
        'SELECT * FROM ProviderModel WHERE providerId = ? AND modelId = ?',
        providerId,
        existingModel.id
      );

      if (!existingProviderModel) {
        // Create new ProviderModel entry if it doesn't exist
        await db.run(
          'INSERT INTO ProviderModel (providerId, modelId) VALUES (?, ?)',
          providerId,
          existingModel.id
        );
        updatedProviderModelsCount++;
      }
    }

    return NextResponse.json({
      message: '模型同步成功',
      newModelsAdded: newModelsCount,
      providerModelsLinked: updatedProviderModelsCount,
    }, { status: 200 });

  } catch (error) {
    console.error("模型同步错误:", error);
    return NextResponse.json({ error: '模型同步失败' }, { status: 500 });
  }
});
