#!/bin/bash
# Test Anthropic Messages API endpoint
# Usage: ./test_anthropic.sh <model> <api_key> [base_url]

set -e

MODEL="${1:-claude-3-5-sonnet-20241022}"
API_KEY="${2:-}"
BASE_URL="${3:-http://localhost:3000/api}"

if [ -z "$API_KEY" ]; then
    echo "Usage: $0 <model> <api_key> [base_url]"
    echo "Example: $0 claude-3-5-sonnet sk-xxx http://localhost:3000"
    exit 1
fi

echo "=== Testing Anthropic Messages API ==="
echo "Model: $MODEL"
echo "Base URL: $BASE_URL"
echo ""

# Test non-streaming with x-api-key header (Anthropic style)
echo "--- Non-streaming test (x-api-key header) ---"
RESPONSE=$(curl -s -w "\nHTTP_CODE:%{http_code}" "$BASE_URL/v1/messages" \
    -H "Content-Type: application/json" \
    -H "x-api-key: $API_KEY" \
    -H "anthropic-version: 2023-06-01" \
    -d '{
        "model": "'"$MODEL"'",
        "max_tokens": 100,
        "messages": [
            {"role": "user", "content": "Say hello in one word"}
        ],
        "stream": false
    }')

HTTP_CODE=$(echo "$RESPONSE" | grep "HTTP_CODE:" | cut -d: -f2)
BODY=$(echo "$RESPONSE" | sed '/HTTP_CODE:/d')

echo "HTTP Status: $HTTP_CODE"
echo "Response:"
echo "$BODY" | jq '.' 2>/dev/null || echo "$BODY"
echo ""

# Test non-streaming with Bearer token (OpenAI style auth)
echo "--- Non-streaming test (Bearer token) ---"
RESPONSE=$(curl -s -w "\nHTTP_CODE:%{http_code}" "$BASE_URL/v1/messages" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $API_KEY" \
    -d '{
        "model": "'"$MODEL"'",
        "max_tokens": 100,
        "messages": [
            {"role": "user", "content": "Say goodbye in one word"}
        ],
        "stream": false
    }')

HTTP_CODE=$(echo "$RESPONSE" | grep "HTTP_CODE:" | cut -d: -f2)
BODY=$(echo "$RESPONSE" | sed '/HTTP_CODE:/d')

echo "HTTP Status: $HTTP_CODE"
echo "Response:"
echo "$BODY" | jq '.' 2>/dev/null || echo "$BODY"
echo ""

# Test streaming
echo "--- Streaming test ---"
curl -s "$BASE_URL/v1/messages" \
    -H "Content-Type: application/json" \
    -H "x-api-key: $API_KEY" \
    -H "anthropic-version: 2023-06-01" \
    -d '{
        "model": "'"$MODEL"'",
        "max_tokens": 50,
        "messages": [
            {"role": "user", "content": "Count from 1 to 5"}
        ],
        "stream": true
    }' | head -30

echo ""
echo "=== Test completed ==="
