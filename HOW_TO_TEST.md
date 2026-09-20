# How to Test RAG System - Quick Guide

## 🚀 Before You Start

Make sure your application is running:

```bash
cd backend-fte
python -m uvicorn app.main:app --reload
```

You should see:
```
INFO:     Uvicorn running on http://127.0.0.1:8000
```

---

## ✅ Option 1: Python Test (Easiest)

### Run the test script:

```bash
# From project root
python test_rag_simple.py
```

### What happens:
1. Asks for your Bearer token
2. Creates a knowledge base
3. Uploads 3 sample documents
4. Searches the documents
5. Builds RAG context
6. Creates an AI agent with RAG
7. Submits a task
8. Checks the result

### Expected output:
```
==================================================
   🧪 RAG System Quick Test
==================================================

📌 Enter your Bearer token: eyJhbGciOiJIUzI1NiIs...
✅ Application running at http://localhost:8000
✅ RAG endpoints are registered
✅ Created KB: 550e8400-e29b-41d4-a716-446655440000
✅ Uploaded: Getting Started
✅ Uploaded: Password Reset
✅ Uploaded: Billing
✅ Documents in KB: 3
✅ Chunks retrieved: 1
✅ Search time: 23ms
✅ Context built with 150 tokens
✅ Created Agent: abc123def456...
✅ Task submitted: xyz789...
✅ Task Status: completed
✅ RAG Augmented: true

==================================================
✅ ALL TESTS PASSED!
==================================================

🎉 RAG System is fully functional!
```

---

## ✅ Option 2: Windows Batch Test

### Run the test script:

```bash
# From project root
run_rag_test.bat "your_bearer_token"
```

**Example:**
```bash
run_rag_test.bat "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
```

---

## ✅ Option 3: Bash Script Test

### Run the test script:

```bash
# From project root
bash run_rag_test.sh "your_bearer_token"
```

---

## ✅ Option 4: Manual cURL Test

### Get your token first:

```bash
# Login to get token
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "password": "password"}'

# Response contains: "access_token": "eyJhbGciOiJ..."
# Copy the token (without quotes)
```

### Run the tests:

```bash
TOKEN="your_token_here"

# 1. Create KB
curl -X POST http://localhost:8000/ai/rag/knowledge-bases \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"Test KB"}'

# 2. Search
curl -X POST "http://localhost:8000/ai/rag/kb/KB_ID/search?query=test" \
  -H "Authorization: Bearer $TOKEN"
```

---

## 🔍 Quick Verification Checklist

After running tests, check these:

### ✓ API Endpoints
```bash
# Should show RAG endpoints
curl http://localhost:8000/docs | grep rag
```

### ✓ Database Tables
```bash
# Connect to PostgreSQL
psql -U postgres -d your_database

# List RAG tables
\dt rag_*
\dt knowledge*

# Count rows
SELECT COUNT(*) FROM rag_documents;
SELECT COUNT(*) FROM rag_chunks;
```

### ✓ Application Logs
Look for:
- "RAG router registered"
- "Document uploaded"
- "Retrieval completed"

---

## 📊 What Each Test Checks

| Test | What It Tests | Expected Result |
|------|---------------|-----------------|
| **1. Health** | App is running | HTTP 200 |
| **2. Endpoints** | RAG routes registered | Endpoints found in /docs |
| **3. Create KB** | Knowledge base creation | KB ID returned (HTTP 201) |
| **4. Upload Docs** | Document upload & indexing | 3 documents created |
| **5. List Docs** | Document retrieval | 3 documents listed |
| **6. Search** | Semantic search | Chunks found |
| **7. Context** | RAG context building | Tokens added > 0 |
| **8. Agent** | RAG-enabled agent creation | Agent created with KB config |
| **9. Task** | Task submission | Task created |
| **10. Result** | Task execution with RAG | `rag_augmented: true` |

---

## ❌ Troubleshooting

### "Cannot connect to application"
```bash
# Make sure app is running:
cd backend-fte
python -m uvicorn app.main:app --reload
```

### "Token is required" or "401 Unauthorized"
```bash
# Get a valid token by logging in:
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "password": "password"}'

# Use the token from response
```

### "RAG endpoints not found"
```bash
# Check if router is registered in main.py:
grep "rag_router" backend-fte/app/main.py

# Should see:
# from app.ai.rag_router import router as rag_router
# app.include_router(rag_router)

# If not, restart app after checking
```

### "Failed to create KB"
```bash
# Check the error response carefully
# Could be:
# - Invalid token (401)
# - Permission issue (403)
# - Database error (500)

# Check application logs for details
```

---

## 🎯 Success Indicators

When tests pass, you should see:
- ✅ All 10 tests passed
- ✅ Knowledge base created
- ✅ Documents indexed
- ✅ Search working
- ✅ RAG context generated
- ✅ Agent with RAG config created
- ✅ Task executed with `rag_augmented: true`

---

## 📚 Next Steps After Successful Test

1. ✅ Tests passed? Great!
2. Read: `backend-fte/app/ai/RAG_QUICKSTART.md`
3. Upload your real documentation
4. Create production knowledge bases
5. Configure agents for your use cases
6. Deploy to production

---

## 📞 Still Having Issues?

Check these files for more help:
- **Detailed guide**: `TESTING_GUIDE.md`
- **Quick start**: `backend-fte/app/ai/RAG_QUICKSTART.md`
- **Full reference**: `backend-fte/app/ai/RAG_GUIDE.md`
- **Technical details**: `backend-fte/app/ai/RAG_IMPLEMENTATION.md`

---

**Happy testing! 🚀**
