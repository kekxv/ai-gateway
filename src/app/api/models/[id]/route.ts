import {NextResponse} from 'next/server';
import {authMiddleware, AuthenticatedRequest} from '@/lib/auth';
import {getInitializedDb} from '@/lib/db';

// GET /api/models/:id - Fetches a single model
export const GET = authMiddleware(async (request: AuthenticatedRequest, {params}: {
  params: Promise<{ id: string }>
}) => {
  const {id} = await params; // Correctly destructure id from params
  try {
    const userId = request.user?.userId;
    const userRole = request.user?.role;
    const db = await getInitializedDb();

    const model = await db.get(
      `SELECT *
       FROM Model
       WHERE id = ? ${userRole !== 'ADMIN' ? 'AND userId = ?' : ''}`,
      id,
      ...(userRole !== 'ADMIN' ? [userId] : [])
    );

    if (!model) {
      return NextResponse.json({error: '模型未找到'}, {status: 404});
    }

    if (model.userId) {
      model.user = await db.get('SELECT id, email, role FROM User WHERE id = ?', model.userId);
    }

    model.modelRoutes = await db.all('SELECT * FROM ModelRoute WHERE modelId = ?', id);

    model.providerModels = await db.all(
      'SELECT * FROM ProviderModel WHERE modelId = ?',
      id
    );

    return NextResponse.json(model);
  } catch (error) {
    console.error(`Error fetching model ${id}:`, error);
    return NextResponse.json({error: '获取模型失败'}, {status: 500});
  }
});

// PUT /api/models/:id - Updates a model
export const PUT = authMiddleware(async (request: AuthenticatedRequest, {params}: {
  params: Promise<{ id: string }>
}) => {
  const {id} = await params; // Correctly destructure id from params
  try {
    const db = await getInitializedDb();
    const body = await request.json();
    const { name, description, alias, modelRoutes, inputTokenPrice, outputTokenPrice } = body;

    // Dynamically build update fields and values
    const updateFields: string[] = [];
    const updateValues: any[] = [];

    if (name !== undefined) {
      updateFields.push('name = ?');
      updateValues.push(name);
    }
    if (description !== undefined) {
      updateFields.push('description = ?');
      updateValues.push(description);
    }
    if (alias !== undefined) {
      updateFields.push('alias = ?');
      updateValues.push(alias);
    }
    if (inputTokenPrice !== undefined) {
      updateFields.push('inputTokenPrice = ?');
      updateValues.push(inputTokenPrice);
    }
    if (outputTokenPrice !== undefined) {
      updateFields.push('outputTokenPrice = ?');
      updateValues.push(outputTokenPrice);
    }

    // Always update updatedAt timestamp
    updateFields.push('updatedAt = CURRENT_TIMESTAMP');

    if (updateFields.length === 0) {
      return NextResponse.json({ error: '没有提供要更新的字段' }, { status: 400 });
    }

    await db.run(
      `UPDATE Model SET ${updateFields.join(', ')} WHERE id = ?`,
      ...updateValues,
      id
    );

    // Update model routes only if modelRoutes is explicitly provided in the body
    if (modelRoutes !== undefined) {
      await db.run('DELETE FROM ModelRoute WHERE modelId = ?', id);
      if (modelRoutes && modelRoutes.length > 0) {
        for (const route of modelRoutes) {
          await db.run(
            'INSERT INTO ModelRoute (modelId, providerId, weight, disabled) VALUES (?, ?, ?, ?)',
            id,
            route.providerId,
            route.weight,
            route.disabled === true // Ensure it's a boolean
          );
        }
      }
    }

    const updatedModel = await db.get('SELECT * FROM Model WHERE id = ?', id); // Use id
    return NextResponse.json(updatedModel);
  } catch (error) {
    console.error(`Error updating model ${id}:`, error); // Keep params.id for logging
    if (error instanceof Error && 'code' in error && (error as { code: string }).code === 'P2002') {
      return NextResponse.json({error: '模型名称已存在'}, {status: 409});
    }
    return NextResponse.json({error: '更新模型失败'}, {status: 500});
  }
});

// DELETE /api/models/:id - Deletes a model
export const DELETE = authMiddleware(async (request: AuthenticatedRequest, {params}: {
  params: Promise<{ id: string }>
}) => {
  const {id} = await params; // Correctly destructure id from params
  try {
    const userId = request.user?.userId;
    const userRole = request.user?.role;
    const db = await getInitializedDb();

    // Check if the model exists and belongs to the user if not an admin
    const existingModel = await db.get(
      `SELECT *
       FROM Model
       WHERE id = ? ${userRole !== 'ADMIN' ? 'AND userId = ?' : ''}`,
      id, // Use id
      ...(userRole !== 'ADMIN' ? [userId] : [])
    );

    if (!existingModel) {
      return NextResponse.json({error: '模型未找到或无权访问'}, {status: 404});
    }

    // The database schema is set up with ON DELETE CASCADE for ModelRoute and ProviderModel,
    // so they will be deleted automatically when the model is deleted.
    await db.run('DELETE FROM Model WHERE id = ?', id); // Use id

    return NextResponse.json({message: '模型已成功删除'});
  } catch (error) {
    console.error(`Error deleting model ${id}:`, error);
    return NextResponse.json({error: '删除模型失败'}, {status: 500});
  }
});
