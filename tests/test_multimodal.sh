#!/bin/bash
# Test multimodal (image/video) support for Anthropic Messages API
# Usage: ./test_multimodal.sh <model> <api_key> [base_url]

set -e

MODEL="${1:-qwen-vl-plus}"
API_KEY="${2:-}"
BASE_URL="${3:-http://localhost:3000/api}"

if [ -z "$API_KEY" ]; then
    echo "Usage: $0 <model> <api_key> [base_url]"
    echo "Example: $0 qwen-vl-plus sk-xxx http://localhost:3000/api"
    exit 1
fi

echo "=== Testing Multimodal (Image/Video) Support ==="
echo "Model: $MODEL"
echo "Base URL: $BASE_URL"
echo ""

# Create a simple 1x1 red pixel PNG image in base64
RED_PIXEL_PNG="iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg=="

# Test 1: Anthropic format with image
echo "--- Test 1: Anthropic format with image ---"
RESPONSE=$(curl -s -w "\nHTTP_CODE:%{http_code}" "$BASE_URL/v1/messages" \
    -H "Content-Type: application/json" \
    -H "x-api-key: $API_KEY" \
    -d '{
        "model": "'"$MODEL"'",
        "max_tokens": 100,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "What color is this pixel?"},
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": "'"$RED_PIXEL_PNG"'"
                        }
                    }
                ]
            }
        ]
    }')

HTTP_CODE=$(echo "$RESPONSE" | grep "HTTP_CODE:" | cut -d: -f2)
BODY=$(echo "$RESPONSE" | sed '/HTTP_CODE:/d')

echo "HTTP Status: $HTTP_CODE"
echo "Response:"
echo "$BODY" | jq '.' 2>/dev/null || echo "$BODY"
echo ""

# Test 2: Anthropic format with video URL
echo "--- Test 2: Anthropic format with video URL ---"
RESPONSE=$(curl -s -w "\nHTTP_CODE:%{http_code}" "$BASE_URL/v1/messages" \
    -H "Content-Type: application/json" \
    -H "x-api-key: $API_KEY" \
    -d '{
        "model": "'"$MODEL"'",
        "max_tokens": 1024,
        "stream": false,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "video",
                        "source": {
                            "type": "url",
                            "url": "https://help-static-aliyun-doc.aliyuncs.com/file-manage-files/zh-CN/20251208/zpupby/3e81ef38-98f0-4d55-bbb6-259334ca18d0.mp4"
                        }
                    },
                    {
                        "type": "text",
                        "text": "Describe this video."
                    }
                ]
            }
        ]
    }')

HTTP_CODE=$(echo "$RESPONSE" | grep "HTTP_CODE:" | cut -d: -f2)
BODY=$(echo "$RESPONSE" | sed '/HTTP_CODE:/d')

echo "HTTP Status: $HTTP_CODE"
echo "Response:"
echo "$BODY" | jq '.' 2>/dev/null || echo "$BODY"
echo ""

# Test 3: OpenAI format with image
echo "--- Test 3: OpenAI format with image ---"
RESPONSE=$(curl -s -w "\nHTTP_CODE:%{http_code}" "$BASE_URL/v1/chat/completions" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $API_KEY" \
    -d '{
        "model": "'"$MODEL"'",
        "max_tokens": 100,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "What color is this pixel?"},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": "data:image/png;base64,'"$RED_PIXEL_PNG"'"
                        }
                    }
                ]
            }
        ]
    }')

HTTP_CODE=$(echo "$RESPONSE" | grep "HTTP_CODE:" | cut -d: -f2)
BODY=$(echo "$RESPONSE" | sed '/HTTP_CODE:/d')

echo "HTTP Status: $HTTP_CODE"
echo "Response:"
echo "$BODY" | jq '.' 2>/dev/null || echo "$BODY"
echo ""

echo "=== Test completed ==="