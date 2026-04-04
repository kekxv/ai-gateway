#!/bin/bash
# Test OpenAI compatible API endpoint
# Usage: ./test_openai.sh <model> <api_key> [base_url]

set -e

MODEL="${1:-gpt-4}"
API_KEY="${2:-}"
BASE_URL="${3:-http://localhost:3000/api}"

if [ -z "$API_KEY" ]; then
    echo "Usage: $0 <model> <api_key> [base_url]"
    echo "Example: $0 gpt-4 sk-xxx http://localhost:3000"
    exit 1
fi

echo "=== Testing OpenAI API ==="
echo "Model: $MODEL"
echo "Base URL: $BASE_URL"
echo ""

# Test non-streaming
echo "--- Non-streaming test ---"
RESPONSE=$(curl -s -w "\nHTTP_CODE:%{http_code}" "$BASE_URL/v1/chat/completions" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $API_KEY" \
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

# Test streaming
echo "--- Streaming test ---"
curl -s "$BASE_URL/v1/chat/completions" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $API_KEY" \
    -d '{
        "model": "'"$MODEL"'",
        "max_tokens": 50,
        "messages": [
            {"role": "user", "content": "Count from 1 to 5"}
        ],
        "stream": true
    }' | head -20

echo ""
echo "=== Test completed ==="
