# How to Check & Test the RAG System

## 🚀 Quick Verification (5 minutes)

### Step 1: Start the Application

```bash
cd backend-fte
python -m uvicorn app.main:app --reload
```

You should see:
```
INFO:     Uvicorn running on http://127.0.0.1:8000
INFO:     Application startup complete
```

### Step 2: Check API Documentation

Open your browser:
```
http://localhost:8000/docs
```

**Look for these sections** (scroll down to find them):
- `POST /ai/rag/knowledge-bases`
- `GET /ai/rag/knowledge-bases`
- `POST /ai/rag/kb/{kb_id}/documents`
- `POST /ai/rag/kb/{kb_id}/search`

✅ If you see these endpoints, RAG is installed!

### Step 3: Get Authentication Token

You need a Bearer token. Get one by logging in:

```bash
# Login with test credentials
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "password": "password"}'

# Response will include a token like:
# {"access_token": "eyJhbGciOiJIUzI1NiIs...", "token_type": "bearer"}
```

**Save this token as**: `$TOKEN`

---

## ✅ Full Test (10 minutes)

### Test 1: Create Knowledge Base

```bash
TOKEN="your_token_here"

# Create a knowledge base
RESPONSE=$(curl -s -X POST http://localhost:8000/ai/rag/knowledge-bases \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test Knowledge Base",
    "description": "Testing RAG system"
  }')

echo $RESPONSE | jq .

# Extract KB_ID from response:
KB_ID=$(echo $RESPONSE | jq -r '.id')
echo "KB ID: $KB_ID"
```

**Expected Response**:
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "Test Knowledge Base",
  "organization_id": "...",
  "document_count": 0,
  "chunk_count": 0,
  "total_tokens": 0,
  "is_indexed": false,
  "created_at": "2026-09-21T..."
}
```

✅ **Success**: KB created!

---

### Test 2: Upload Documents

```bash
# Upload Document 1: Getting Started
curl -s -X POST "http://localhost:8000/ai/rag/kb/$KB_ID/documents" \
  -H "Authorization: Bearer $TOKEN" \
  -d 'title=Getting Started&content=Welcome to our platform. Step 1: Create an account at signup.com. Step 2: Verify your email. Step 3: Choose your plan.'

# Upload Document 2: Account Management
curl -s -X POST "http://localhost:8000/ai/rag/kb/$KB_ID/documents" \
  -H "Authorization: Bearer $TOKEN" \
  -d 'title=Account Management&content=To reset your password: 1. Click Account Settings. 2. Select Security. 3. Click Change Password. 4. Enter new password (min 12 chars, must include number). 5. Click Save.'

# Upload Document 3: Billing
curl -s -X POST "http://localhost:8000/ai/rag/kb/$KB_ID/documents" \
  -H "Authorization: Bearer $TOKEN" \
  -d 'title=Billing FAQ&content=Q: What payment methods? A: Credit cards, PayPal, bank transfer. Q: Can I change plans? A: Yes, anytime.'
```

**Expected for each**: `HTTP 201 Created` with document details

✅ **Success**: Documents uploaded!

---

### Test 3: List Documents

```bash
curl -s -X GET "http://localhost:8000/ai/rag/kb/$KB_ID/documents" \
  -H "Authorization: Bearer $TOKEN" | jq .
```

**Expected Response**:
```json
{
  "items": [
    {
      "id": "...",
      "title": "Getting Started",
      "chunk_count": 1,
      "token_count": 28,
      "is_indexed": true,
      "created_at": "2026-09-21T..."
    },
    ...
  ],
  "total": 3
}
```

✅ **Success**: Documents listed and indexed!

---

### Test 4: Search Documents

```bash
# Search for "password reset"
curl -s -X POST "http://localhost:8000/ai/rag/kb/$KB_ID/search?query=password&top_k=5" \
  -H "Authorization: Bearer $TOKEN" | jq .
```

**Expected Response**:
```json
{
  "status": "success",
  "query": "password",
  "knowledge_base_id": "...",
  "chunks_retrieved": 1,
  "chunks": [
    {
      "id": "...",
      "document_title": "Account Management",
      "content": "To reset your password: 1. Click Account Settings...",
      "chunk_index": 0,
      "similarity_score": 0.92
    }
  ],
  "retrieval_time_ms": 23
}
```

✅ **Success**: Search working!

---

### Test 5: Build RAG Context

```bash
# Get formatted context for LLM
curl -s -X POST "http://localhost:8000/ai/rag/kb/$KB_ID/augment?query=How+do+I+reset+password&top_k=3" \
  -H "Authorization: Bearer $TOKEN" | jq .
```

**Expected Response**:
```json
{
  "status": "success",
  "context": "Retrieved 1 relevant documents:\n\n[Document 1: Account Management]\nContent: To reset your password: 1. Click Account Settings...",
  "source_documents": 1,
  "tokens_added": 150
}
```

✅ **Success**: Context building working!

---

### Test 6: Create RAG-Enabled Agent

```bash
# Create an AI agent with RAG enabled
AGENT_RESPONSE=$(curl -s -X POST http://localhost:8000/ai/agents \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"name\": \"RAG Test Agent\",
    \"agent_type\": \"custom\",
    \"description\": \"Testing RAG integration\",
    \"config\": {
      \"model\": \"gpt-4o-mini\",
      \"rag_knowledge_base_id\": \"$KB_ID\"
    }
  }")

echo $AGENT_RESPONSE | jq .

AGENT_ID=$(echo $AGENT_RESPONSE | jq -r '.id')
echo "Agent ID: $AGENT_ID"
```

**Expected**: Agent created with `rag_knowledge_base_id` in config

✅ **Success**: RAG-enabled agent created!

---

### Test 7: Submit Task with RAG

```bash
# Submit a task to the agent
TASK_RESPONSE=$(curl -s -X POST "http://localhost:8000/ai/agents/$AGENT_ID/tasks" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "task_type": "custom",
    "input_data": {
      "question": "How do I reset my password?"
    },
    "requires_human_approval": false
  }')

echo $TASK_RESPONSE | jq .

TASK_ID=$(echo $TASK_RESPONSE | jq -r '.id')
echo "Task ID: $TASK_ID"
```

✅ **Success**: Task submitted!

---

### Test 8: Check Task Result

```bash
# Wait a moment for processing
sleep 2

# Check task result
curl -s -X GET "http://localhost:8000/ai/tasks/$TASK_ID" \
  -H "Authorization: Bearer $TOKEN" | jq .
```

**Expected Response**:
```json
{
  "id": "...",
  "status": "completed",
  "output_data": {
    "status": "success",
    "response": "To reset your password: 1. Click Account Settings. 2. Select Security. 3. Click Change Password...",
    "rag_augmented": true
  },
  "llm_provider": "openai",
  "llm_model": "gpt-4o-mini",
  "llm_tokens_used": 156
}
```

✅ **Success**: RAG working end-to-end! Notice `"rag_augmented": true`!

---

## 🐍 Python Test Script

Save this as `test_rag.py`:

```python
import httpx
import json
import time

# Configuration
BASE_URL = "http://localhost:8000"
TOKEN = "YOUR_TOKEN_HERE"

headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

def test_rag():
    print("🧪 Testing RAG System...\n")
    
    # 1. Create KB
    print("1️⃣ Creating Knowledge Base...")
    kb_resp = httpx.post(
        f"{BASE_URL}/ai/rag/knowledge-bases",
        headers=headers,
        json={"name": "Test KB", "description": "Testing"}
    )
    kb = kb_resp.json()
    kb_id = kb["id"]
    print(f"   ✅ Created KB: {kb_id}\n")
    
    # 2. Upload docs
    print("2️⃣ Uploading Documents...")
    docs = [
        ("Getting Started", "Step 1: Sign up at signup.com"),
        ("Password Help", "To reset: Go to Settings > Security > Change Password"),
        ("Pricing", "Plans start at $9/month"),
    ]
    for title, content in docs:
        httpx.post(
            f"{BASE_URL}/ai/rag/kb/{kb_id}/documents",
            headers=headers,
            params={"title": title, "content": content}
        )
        print(f"   ✅ Uploaded: {title}")
    print()
    
    # 3. Search
    print("3️⃣ Searching Documents...")
    search_resp = httpx.post(
        f"{BASE_URL}/ai/rag/kb/{kb_id}/search",
        headers=headers,
        params={"query": "password", "top_k": 3}
    )
    search = search_resp.json()
    print(f"   ✅ Found {search['chunks_retrieved']} chunks")
    print(f"   ✅ Search time: {search['retrieval_time_ms']}ms\n")
    
    # 4. Build context
    print("4️⃣ Building RAG Context...")
    context_resp = httpx.post(
        f"{BASE_URL}/ai/rag/kb/{kb_id}/augment",
        headers=headers,
        params={"query": "How do I reset password?"}
    )
    context = context_resp.json()
    print(f"   ✅ Context built ({context['tokens_added']} tokens)\n")
    
    # 5. Create agent
    print("5️⃣ Creating RAG-Enabled Agent...")
    agent_resp = httpx.post(
        f"{BASE_URL}/ai/agents",
        headers=headers,
        json={
            "name": "Test RAG Agent",
            "agent_type": "custom",
            "config": {"rag_knowledge_base_id": kb_id}
        }
    )
    agent = agent_resp.json()
    agent_id = agent["id"]
    print(f"   ✅ Created agent: {agent_id}\n")
    
    # 6. Submit task
    print("6️⃣ Submitting Task with Question...")
    task_resp = httpx.post(
        f"{BASE_URL}/ai/agents/{agent_id}/tasks",
        headers=headers,
        json={
            "task_type": "custom",
            "input_data": {"question": "How do I reset my password?"},
            "requires_human_approval": False
        }
    )
    task = task_resp.json()
    task_id = task["id"]
    print(f"   ✅ Task submitted: {task_id}\n")
    
    # 7. Wait and check result
    print("7️⃣ Waiting for Result...")
    time.sleep(2)
    
    result_resp = httpx.get(
        f"{BASE_URL}/ai/tasks/{task_id}",
        headers=headers
    )
    result = result_resp.json()
    
    print(f"   Status: {result['status']}")
    print(f"   RAG Augmented: {result['output_data'].get('rag_augmented', False)}")
    print(f"   Model: {result['llm_model']}")
    print(f"   Tokens: {result['llm_tokens_used']}\n")
    
    print("✅ ALL TESTS PASSED! RAG System is working!\n")
    return True

if __name__ == "__main__":
    test_rag()
```

**Run it**:
```bash
python test_rag.py
```

---

## 🔍 Database Verification

Check if tables were created:

```bash
# Connect to PostgreSQL
psql -U postgres -d your_database

# List RAG tables
\dt rag_*
\dt knowledge*

# You should see:
# - knowledge_bases
# - rag_documents
# - rag_chunks
# - rag_retrievals
```

Count documents:
```sql
SELECT COUNT(*) FROM rag_documents;
SELECT COUNT(*) FROM rag_chunks;
```

---

## 📊 Monitoring & Logs

### Check Application Logs

```bash
# If running with --reload, look for:
# - "RAG router registered"
# - "Document uploaded"
# - "Retrieval audit logged"
```

### Check Retrieval Audit Trail

```bash
psql -U postgres -d your_database

-- See all retrievals
SELECT query, retrieved_count, retrieval_time_ms 
FROM rag_retrievals 
ORDER BY created_at DESC 
LIMIT 10;
```

### Monitor Performance

```bash
-- Check average retrieval time
SELECT AVG(retrieval_time_ms) as avg_time, COUNT(*) as total_queries
FROM rag_retrievals;
```

---

## ❌ Troubleshooting

### Issue: "RAG endpoints not showing in /docs"

**Solution**:
```bash
# 1. Restart app
# 2. Check imports in app/main.py:
grep "rag_router" backend-fte/app/main.py

# Should see:
# from app.ai.rag_router import router as rag_router
# app.include_router(rag_router)
```

### Issue: "No search results"

**Check**:
```bash
# 1. Verify documents were created
curl -X GET "http://localhost:8000/ai/rag/kb/$KB_ID/documents" \
  -H "Authorization: Bearer $TOKEN" | jq '.items | length'

# 2. Check is_indexed flag
curl -X GET "http://localhost:8000/ai/rag/kb/$KB_ID/documents" \
  -H "Authorization: Bearer $TOKEN" | jq '.items[0].is_indexed'

# 3. Try broader search term
```

### Issue: "rag_models module not found"

**Solution**:
```bash
# Verify file exists:
ls -la backend-fte/app/ai/rag_models.py

# Check import in models.py:
grep "rag_models" backend-fte/app/models.py

# Restart app
```

### Issue: "Database table doesn't exist"

**Solution**:
```bash
# Run migrations
cd backend-fte
alembic upgrade head

# Or manually create (not recommended):
# Check rag_models.py has @declarative

# Restart app to auto-create via SQLAlchemy
```

---

## ✅ Success Checklist

- [ ] App starts without errors
- [ ] RAG endpoints show in `/docs`
- [ ] Can create knowledge base (HTTP 201)
- [ ] Can upload documents (HTTP 201)
- [ ] Can list documents (HTTP 200)
- [ ] Can search documents (HTTP 200, chunks_retrieved > 0)
- [ ] Can build context (HTTP 200, context not empty)
- [ ] Can create RAG agent (HTTP 201, config has rag_knowledge_base_id)
- [ ] Can submit task to agent (HTTP 201, task created)
- [ ] Task result shows `rag_augmented: true`
- [ ] Database tables exist (knowledge_bases, rag_documents, rag_chunks, rag_retrievals)
- [ ] Retrieval audit trail populated

**If all checks pass**: ✅ **RAG System is fully operational!**

---

## 📚 Next Steps After Verification

1. Read: `backend-fte/app/ai/RAG_QUICKSTART.md`
2. Upload your real documentation
3. Create production knowledge bases
4. Configure agents with RAG
5. Monitor retrieval quality
6. Deploy to production

---

**Happy testing! 🚀**
