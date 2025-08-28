import { NextResponse } from 'next/server';
import { PrismaClient } from '@prisma/client';
import { authMiddleware, AuthenticatedRequest } from '@/lib/auth'; // Import authMiddleware and AuthenticatedRequest

const prisma = new PrismaClient();

export const POST = authMiddleware(async (request: AuthenticatedRequest) => {
  try {
    const body = await request.json();
    const { channelId, modelId, prompt } = body; // Now accepts channelId and modelId

    if (!channelId || !modelId || !prompt) {
      return NextResponse.json({ error: '缺少渠道 ID、模型 ID 或提示' }, { status: 400 });
    }

    // Find a ModelRoute for the given channelId and modelId
    const modelRoute = await prisma.modelRoute.findFirst({
      where: {
        channelId: parseInt(channelId),
        modelId: parseInt(modelId),
        channel: { enabled: true }, // Assuming channels have an 'enabled' field
      },
      include: {
        model: true, // Include the related model data
        channel: {
          include: {
            provider: true,
          },
        },
      },
    });

    if (!modelRoute) {
      return NextResponse.json({ error: `未找到渠道 ${channelId} 和模型 ${modelId} 的路由` }, { status: 404 });
    }

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
