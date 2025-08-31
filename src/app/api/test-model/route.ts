import { NextResponse } from 'next/server';
import { authMiddleware, AuthenticatedRequest } from '@/lib/auth'; // Import authMiddleware and AuthenticatedRequest
import { getInitializedDb } from '@/lib/db';

export const POST = authMiddleware(async (request: AuthenticatedRequest) => {
  try {
    const body = await request.json();
    const { channelId, modelId, prompt } = body; // Now accepts channelId and modelId

    if (!channelId || !modelId || !prompt) {
      return NextResponse.json({ error: '缺少渠道 ID、模型 ID 或提示' }, { status: 400 });
    }

    // Find a ModelRoute for the given channelId and modelId
    const db = await getInitializedDb();

    const modelRoute = await db.get(
      `SELECT mr.*, m.name as modelName, c.name as channelName
       FROM ModelRoute mr
       JOIN Model m ON mr.modelId = m.id
       JOIN Channel c ON mr.channelId = c.id
       WHERE mr.channelId = ? AND mr.modelId = ? AND c.enabled = TRUE`,
      parseInt(channelId),
      parseInt(modelId)
    );

    if (!modelRoute) {
      return NextResponse.json({ error: `未找到渠道 ${channelId} 和模型 ${modelId} 的路由` }, { status: 404 });
    }

    // Fetch one provider associated with the channel for testing
    const channelProvider = await db.get(
      `SELECT cp.providerId, p.name, p.baseURL, p.apiKey
       FROM ChannelProvider cp
       JOIN Provider p ON cp.providerId = p.id
       WHERE cp.channelId = ?
       ORDER BY cp.providerId LIMIT 1`, // Pick one provider for testing
      parseInt(channelId)
    );

    if (!channelProvider) {
      return NextResponse.json({ error: `渠道 ${channelId} 没有关联的提供商` }, { status: 404 });
    }

    // Attach provider details to modelRoute.channel
    modelRoute.model = { name: modelRoute.modelName };
    modelRoute.channel = {
      name: modelRoute.channelName,
      provider: {
        name: channelProvider.name,
        baseURL: channelProvider.baseURL,
        apiKey: channelProvider.apiKey,
      },
    };

    const { channel } = modelRoute;
    const { provider } = channel;

    // Construct the request body for the upstream AI service
    const upstreamRequestBody = {
      model: modelRoute.model.name, // Use the actual model name from the ModelRoute
      messages: [{ role: "user", content: prompt }],
      // Add other parameters as needed for the specific AI service
    };

    // Forward the request to the upstream AI service
    const targetUrl = `${provider.baseURL}/chat/completions`; // Assuming a chat completions endpoint

    const upstreamResponse = await fetch(targetUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${channel.provider.apiKey}`,
      },
      body: JSON.stringify(upstreamRequestBody),
      // @ts-expect-error - duplex is required for streaming in Node.js
      duplex: 'half', // Required for streaming in Node.js
    });

    if (!upstreamResponse.ok) {
      const errorData = await upstreamResponse.json();
      return NextResponse.json({ error: `上游服务错误: ${errorData.message || upstreamResponse.statusText}` }, { status: upstreamResponse.status});
    }

    const responseData = await upstreamResponse.json();
    return NextResponse.json(responseData);

  } catch (error) {
    console.error("模型测试错误:", error);
    return NextResponse.json({ error: '执行模型测试失败' }, { status: 500 });
  }
});
