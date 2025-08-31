import { NextResponse } from 'next/server';
import { authMiddleware, AuthenticatedRequest } from '@/lib/auth';
import { getInitializedDb } from '@/lib/db';

// Function to sync models from providers with autoLoadModels enabled
async function syncProviderModels(db: any) {
  try {
    // Get all providers with autoLoadModels enabled
    const providers = await db.all('SELECT * FROM Provider WHERE autoLoadModels = 1');
    
    let totalNewModels = 0;
    let totalLinkedModels = 0;
    
    for (const provider of providers) {
      try {
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
            console.error(`Failed to fetch models from OpenAI provider ${provider.id}: ${openaiRawText}`);
            continue;
          }

          try {
            const openaiData = JSON.parse(openaiRawText);
            modelsToFetch = openaiData.data.map((model: any) => ({
              id: model.id,
              name: model.id,
              description: model.object,
            }));
          } catch (e) {
            console.error(`Failed to parse OpenAI model data for provider ${provider.id}:`, e);
            continue;
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
            console.error(`Failed to fetch models from Gemini provider ${provider.id}: ${errorText}`);
            continue;
          }

          const geminiData = await geminiResponse.json();
          modelsToFetch = geminiData.models.map((model: any) => ({
            id: model.name,
            name: model.displayName || model.name,
            description: model.description,
          }));

        } else {
          console.warn(`Unsupported provider type for auto-loading: ${provider.type}`);
          continue;
        }

        // Compare and update database
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
            provider.id,
            existingModel.id
          );

          if (!existingProviderModel) {
            // Create new ProviderModel entry if it doesn't exist
            await db.run(
              'INSERT INTO ProviderModel (providerId, modelId) VALUES (?, ?)',
              provider.id,
              existingModel.id
            );
            updatedProviderModelsCount++;
          }
        }
        
        totalNewModels += newModelsCount;
        totalLinkedModels += updatedProviderModelsCount;
        
        if (newModelsCount > 0 || updatedProviderModelsCount > 0) {
          console.log(`Auto-synced provider ${provider.id}: ${newModelsCount} new models, ${updatedProviderModelsCount} linked models`);
        }
      } catch (error) {
        console.error(`Error syncing models for provider ${provider.id}:`, error);
      }
    }
    
    if (totalNewModels > 0 || totalLinkedModels > 0) {
      console.log(`Auto-sync completed: ${totalNewModels} new models, ${totalLinkedModels} linked models`);
    }
  } catch (error) {
    console.error("Error in auto-sync process:", error);
  }
}

// GET /api/models - Fetches all models
export const GET = authMiddleware(async (request: AuthenticatedRequest) => {
  try {
    const userId = request.user?.userId;
    const userRole = request.user?.role;

    const db = await getInitializedDb();

    // Auto-sync models from providers with autoLoadModels enabled
    await syncProviderModels(db);

    const models = await db.all(
      `SELECT * FROM Model ${userRole !== 'ADMIN' ? 'WHERE userId = ?' : ''} ORDER BY createdAt DESC`,
      ...(userRole !== 'ADMIN' ? [userId] : [])
    );

    for (const model of models) {
      if (model.userId) {
        model.user = await db.get('SELECT id, email, role FROM User WHERE id = ?', model.userId);
      }
      const rawModelRoutes = await db.all(
        `SELECT mr.*, c.name as channelName
         FROM ModelRoute mr
         JOIN Channel c ON mr.channelId = c.id
         WHERE mr.modelId = ?`,
        model.id
      );

      model.modelRoutes = [];
      for (const mr of rawModelRoutes) {
        const channelProviders = await db.all(
          'SELECT cp.providerId, p.name FROM ChannelProvider cp JOIN Provider p ON cp.providerId = p.id WHERE cp.channelId = ?',
          mr.channelId
        );
        model.modelRoutes.push({
          ...mr,
          providers: channelProviders.map((cp: any) => ({ id: cp.providerId, name: cp.name })) // Attach providers
        });
      }
      model.providerModels = await db.all(
        'SELECT * FROM ProviderModel WHERE modelId = ?',
        model.id
      );
    }
    return NextResponse.json(models, {
      headers: {
        'Cache-Control': 'no-store, no-cache, must-revalidate, proxy-revalidate',
        'Pragma': 'no-cache',
        'Expires': '0',
      },
    });
  } catch (error) {
    console.error("Error fetching models:", error);
    return NextResponse.json({ error: '获取模型失败' }, { status: 500 });
  }
});

// POST /api/models - Creates one or more models and associates them with a provider
export const POST = authMiddleware(async (request: AuthenticatedRequest) => {
  try {
    const userId = request.user?.userId;
    if (!userId) {
      return NextResponse.json({ error: '未授权: 用户ID缺失' }, { status: 401 });
    }

    const body = await request.json();
    const { models, providerId } = body; // For batch creation from model selection modal
    const { name, description, alias, modelRoutes } = body; // For single model creation from form, added alias

    const db = await getInitializedDb();

    // Batch creation logic
    if (Array.isArray(models) && providerId) {
      const createdModels = [];
      for (const modelData of models) {
        const existingModel = await db.get('SELECT * FROM Model WHERE name = ?', modelData.name);

        let modelId: number;

        if (!existingModel) {
          const result = await db.run(
            'INSERT INTO Model (name, description, alias, userId) VALUES (?, ?, ?, ?)', // Added alias
            modelData.name,
            modelData.description,
            modelData.alias || null, // Use alias from modelData or null
            userId
          );
          modelId = result.lastID;
          createdModels.push({ id: modelId, name: modelData.name, description: modelData.description, alias: modelData.alias });
        } else {
          modelId = existingModel.id;
        }

        // Associate model with the provider if not already associated
        const existingProviderModel = await db.get(
          'SELECT * FROM ProviderModel WHERE providerId = ? AND modelId = ?',
          providerId,
          modelId
        );

        if (!existingProviderModel) {
          await db.run(
            'INSERT INTO ProviderModel (providerId, modelId) VALUES (?, ?)',
            providerId,
            modelId
          );
        }
      }
      return NextResponse.json({ message: `成功添加 ${createdModels.length} 个新模型`, createdModels }, { status: 201 });
    }

    // Single creation logic
    if (name) {
      const result = await db.run(
        'INSERT INTO Model (name, description, alias, userId) VALUES (?, ?, ?, ?)', // Added alias
        name,
        description,
        alias || null, // Use alias from body or null
        userId
      );
      const newModelId = result.lastID;

      if (modelRoutes && modelRoutes.length > 0) {
        for (const route of modelRoutes) {
          await db.run(
            'INSERT INTO ModelRoute (modelId, channelId, weight) VALUES (?, ?, ?)',
            newModelId,
            route.channelId,
            route.weight
          );
        }
      }
      const newModel = await db.get('SELECT * FROM Model WHERE id = ?', newModelId);
      return NextResponse.json(newModel, { status: 201 });
    }

    return NextResponse.json({ error: '无效的请求体' }, { status: 400 });

  } catch (error) {
    console.error("Error creating model:", error);
    if (error instanceof Error && 'code' in error && (error as { code: string }).code === 'P2002') {
      return NextResponse.json({ error: '一个或多个模型名称已存在' }, { status: 409 });
    }
    return NextResponse.json({ error: '创建模型失败' }, { status: 500 });
  }
});
