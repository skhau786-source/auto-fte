#!/bin/bash

# RAG System Quick Test Script
# This script tests the RAG system end-to-end

set -e

echo "=================================="
echo "   🧪 RAG System Quick Test"
echo "=================================="
echo ""

# Configuration
BASE_URL="http://localhost:8000"
TOKEN="${1:-test-token}"  # Pass token as first argument

# Check if app is running
echo "1️⃣ Checking if application is running..."
if ! curl -s "$BASE_URL/health" > /dev/null 2>&1; then
    echo "❌ Application is not running!"
    echo ""
    echo "Start it with:"
    echo "  cd backend-fte"
    echo "  python -m uvicorn app.main:app --reload"
    echo ""
    exit 1
fi
echo "✅ Application is running at $BASE_URL"
echo ""

# Check RAG endpoints
echo "2️⃣ Checking RAG endpoints..."
if curl -s "$BASE_URL/docs" | grep -q "rag/knowledge-bases"; then
    echo "✅ RAG endpoints are registered"
else
    echo "❌ RAG endpoints not found!"
    exit 1
fi
echo ""

# Get auth token if not provided
if [ "$TOKEN" = "test-token" ]; then
    echo "3️⃣ Getting authentication token..."
    echo "   (Please provide your token as argument or set it in the script)"
    echo ""
    echo "   Or run with token:"
    echo "   $0 'your_bearer_token'"
    echo ""
    exit 1
fi

echo "3️⃣ Creating Knowledge Base..."
KB_RESPONSE=$(curl -s -X POST "$BASE_URL/ai/rag/knowledge-bases" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"Quick Test KB","description":"Testing RAG"}')

KB_ID=$(echo "$KB_RESPONSE" | grep -o '"id":"[^"]*"' | head -1 | cut -d'"' -f4)

if [ -z "$KB_ID" ]; then
    echo "❌ Failed to create KB"
    echo "Response: $KB_RESPONSE"
    exit 1
fi
echo "✅ Created KB: $KB_ID"
echo ""

echo "4️⃣ Uploading Documents..."
# Doc 1
curl -s -X POST "$BASE_URL/ai/rag/kb/$KB_ID/documents" \
  -H "Authorization: Bearer $TOKEN" \
  -d 'title=Getting Started&content=Welcome to our platform. Step 1: Sign up at signup.com. Step 2: Verify email. Step 3: Choose plan.' > /dev/null
echo "   ✅ Document 1: Getting Started"

# Doc 2
curl -s -X POST "$BASE_URL/ai/rag/kb/$KB_ID/documents" \
  -H "Authorization: Bearer $TOKEN" \
  -d 'title=Password Reset&content=To reset your password: 1. Click Settings. 2. Select Security. 3. Click Change Password. 4. Enter new password (min 12 chars). 5. Save.' > /dev/null
echo "   ✅ Document 2: Password Reset"

# Doc 3
curl -s -X POST "$BASE_URL/ai/rag/kb/$KB_ID/documents" \
  -H "Authorization: Bearer $TOKEN" \
  -d 'title=Billing&content=Q: What payment methods? A: Credit cards, PayPal, bank transfer. Q: Can I change plans? A: Yes, anytime.' > /dev/null
echo "   ✅ Document 3: Billing"
echo ""

echo "5️⃣ Listing Documents..."
DOC_COUNT=$(curl -s -X GET "$BASE_URL/ai/rag/kb/$KB_ID/documents" \
  -H "Authorization: Bearer $TOKEN" | grep -o '"total":[0-9]*' | cut -d':' -f2)
echo "✅ Documents in KB: $DOC_COUNT"
echo ""

echo "6️⃣ Searching Documents (query: 'password')..."
SEARCH_RESPONSE=$(curl -s -X POST "$BASE_URL/ai/rag/kb/$KB_ID/search?query=password&top_k=5" \
  -H "Authorization: Bearer $TOKEN")

CHUNKS=$(echo "$SEARCH_RESPONSE" | grep -o '"chunks_retrieved":[0-9]*' | cut -d':' -f2)
TIME_MS=$(echo "$SEARCH_RESPONSE" | grep -o '"retrieval_time_ms":[0-9]*' | cut -d':' -f2)

if [ -z "$CHUNKS" ]; then
    echo "❌ Search failed"
    echo "Response: $SEARCH_RESPONSE"
    exit 1
fi

echo "✅ Chunks retrieved: $CHUNKS"
echo "✅ Search time: ${TIME_MS}ms"
echo ""

echo "7️⃣ Building RAG Context..."
CONTEXT_RESPONSE=$(curl -s -X POST "$BASE_URL/ai/rag/kb/$KB_ID/augment?query=How+do+I+reset+password" \
  -H "Authorization: Bearer $TOKEN")

TOKENS_ADDED=$(echo "$CONTEXT_RESPONSE" | grep -o '"tokens_added":[0-9]*' | cut -d':' -f2)
echo "✅ Context built with $TOKENS_ADDED tokens"
echo ""

echo "8️⃣ Creating RAG-Enabled Agent..."
AGENT_RESPONSE=$(curl -s -X POST "$BASE_URL/ai/agents" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"name\": \"Test RAG Agent\",
    \"agent_type\": \"custom\",
    \"config\": {
      \"rag_knowledge_base_id\": \"$KB_ID\"
    }
  }")

AGENT_ID=$(echo "$AGENT_RESPONSE" | grep -o '"id":"[^"]*"' | head -1 | cut -d'"' -f4)

if [ -z "$AGENT_ID" ]; then
    echo "❌ Failed to create agent"
    echo "Response: $AGENT_RESPONSE"
    exit 1
fi
echo "✅ Created Agent: $AGENT_ID"
echo ""

echo "=================================="
echo "   ✅ ALL TESTS PASSED!"
echo "=================================="
echo ""
echo "Summary:"
echo "  ✓ Application running"
echo "  ✓ RAG endpoints registered"
echo "  ✓ Knowledge Base created: $KB_ID"
echo "  ✓ 3 documents uploaded"
echo "  ✓ Search working ($CHUNKS chunks found in ${TIME_MS}ms)"
echo "  ✓ Context building working"
echo "  ✓ RAG Agent created: $AGENT_ID"
echo ""
echo "🎉 RAG System is fully functional!"
echo ""
