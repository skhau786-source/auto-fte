# RAG Quick Start — 5 Minutes

Get your AI chatbot using RAG in 5 minutes.

## The Scenario

You have a support chatbot that needs to answer questions using your documentation.

### Without RAG ❌
```
User: "How do I reset my password?"
LLM: "You can typically reset your password by clicking the forgot password link..."
     (Generic answer, may not match YOUR product)
```

### With RAG ✅
```
User: "How do I reset my password?"
System: Retrieves: [Your Guide: Account Reset PDF] + [FAQ: Password Reset]
LLM: "In our product, go to Settings > Security > Change Password. 
      Your password must be 12+ characters..."
     (Accurate answer from YOUR documentation)
```

## 5-Minute Setup

### Step 1: Create Knowledge Base (1 min)

```bash
# Create a knowledge base for your docs
curl -X POST http://localhost:8000/ai/rag/knowledge-bases \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Support Docs",
    "description": "Customer support documentation",
    "embedding_model": "openai/text-embedding-3-small"
  }'

# Save the returned KB ID: "kb-12345"
```

### Step 2: Upload Documents (2 min)

```bash
# Document 1: Getting Started Guide
curl -X POST "http://localhost:8000/ai/rag/kb/kb-12345/documents" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d 'title=Getting Started Guide&content=Welcome to our platform. Step 1: Create an account at signup.com. Step 2: Verify your email. Step 3: Choose your plan.'

# Document 2: Account Management
curl -X POST "http://localhost:8000/ai/rag/kb/kb-12345/documents" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d 'title=Account Management&content=To reset your password: 1. Click Account Settings. 2. Select Security. 3. Click Change Password. 4. Enter new password (min 12 chars, must include number). 5. Click Save.'

# Document 3: Billing FAQ
curl -X POST "http://localhost:8000/ai/rag/kb/kb-12345/documents" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d 'title=Billing FAQ&content=Q: What payment methods do you accept? A: We accept all major credit cards, PayPal, and bank transfer. Q: Can I change my plan? A: Yes, you can upgrade or downgrade anytime.'
```

### Step 3: Create AI Agent with RAG (1 min)

```bash
# Create support agent that uses RAG
curl -X POST http://localhost:8000/ai/agents \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Support Bot",
    "agent_type": "custom",
    "description": "Customer support assistant using RAG",
    "config": {
      "model": "gpt-4o-mini",
      "rag_knowledge_base_id": "kb-12345"
    }
  }'

# Save the agent ID: "agent-xyz"
```

### Step 4: Ask Your Agent (1 min)

```bash
# Submit a task to the agent
curl -X POST http://localhost:8000/ai/agents/agent-xyz/tasks \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "task_type": "custom",
    "input_data": {
      "question": "How do I reset my password?"
    },
    "requires_human_approval": false
  }'

# Check the response
curl -X GET http://localhost:8000/ai/tasks/task-id \
  -H "Authorization: Bearer YOUR_TOKEN"
```

Response:
```json
{
  "status": "completed",
  "output_data": {
    "status": "success",
    "response": "In our platform, to reset your password: 1. Click Account Settings. 2. Select Security. 3. Click Change Password. 4. Enter your new password (minimum 12 characters, must include at least one number). 5. Click Save. Your password will be updated immediately.",
    "rag_augmented": true
  }
}
```

✅ Done! Your chatbot is now using RAG!

---

## Python Example

If you prefer Python:

```python
import httpx

# 1. Create KB
kb_response = httpx.post(
    "http://localhost:8000/ai/rag/knowledge-bases",
    headers={"Authorization": "Bearer TOKEN"},
    json={
        "name": "Support Docs",
        "description": "Customer documentation",
    }
)
kb_id = kb_response.json()["id"]

# 2. Upload docs
docs = [
    ("Getting Started", "Step 1: Sign up..."),
    ("Password Reset", "Go to Settings > Security..."),
    ("Billing", "We accept credit cards..."),
]

for title, content in docs:
    httpx.post(
        f"http://localhost:8000/ai/rag/kb/{kb_id}/documents",
        headers={"Authorization": "Bearer TOKEN"},
        params={"title": title, "content": content},
    )

# 3. Create agent
agent_response = httpx.post(
    "http://localhost:8000/ai/agents",
    headers={"Authorization": "Bearer TOKEN"},
    json={
        "name": "Support Bot",
        "config": {"rag_knowledge_base_id": kb_id},
    }
)
agent_id = agent_response.json()["id"]

# 4. Submit task
task_response = httpx.post(
    f"http://localhost:8000/ai/agents/{agent_id}/tasks",
    headers={"Authorization": "Bearer TOKEN"},
    json={
        "task_type": "custom",
        "input_data": {"question": "How do I reset my password?"},
    }
)

task_id = task_response.json()["id"]

# 5. Get response
task = httpx.get(
    f"http://localhost:8000/ai/tasks/{task_id}",
    headers={"Authorization": "Bearer TOKEN"},
).json()

print(f"Bot: {task['output_data']['response']}")
# Bot: In our platform, to reset your password...
```

---

## Testing Locally

### 1. Start the server
```bash
cd backend-fte
python -m uvicorn app.main:app --reload
```

### 2. Get a test token
```bash
# Register/login to get a valid token
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "password": "password"}'

# Save the token from response
```

### 3. Run the quick start above

---

## Common Use Cases

### Use Case 1: FAQ Automation
```
KB: FAQ document
Query: "What's your refund policy?"
Response: Pulls from FAQ, gives exact policy
```

### Use Case 2: Product Documentation
```
KB: User guides, API docs, troubleshooting
Query: "How do I integrate with Shopify?"
Response: Pulls integration guide, gives step-by-step
```

### Use Case 3: Internal Knowledge Base
```
KB: Company policies, procedures, architecture
Query: "What's our data retention policy?"
Response: Pulls policy document, gives accurate answer
```

### Use Case 4: Technical Support
```
KB: Error codes, solutions, troubleshooting steps
Query: "I'm getting error 500"
Response: Pulls error guide, suggests solutions
```

---

## Advanced: Verify It Works

### Search Your Knowledge Base

```bash
curl -X POST "http://localhost:8000/ai/rag/kb/kb-12345/search?query=password&top_k=3" \
  -H "Authorization: Bearer TOKEN"
```

Response:
```json
{
  "status": "success",
  "query": "password",
  "chunks_retrieved": 2,
  "chunks": [
    {
      "document_title": "Account Management",
      "content": "To reset your password: 1. Click Account Settings...",
      "similarity_score": 0.92
    },
    {
      "document_title": "Security Guide",
      "content": "Password requirements: minimum 12 characters...",
      "similarity_score": 0.85
    }
  ]
}
```

### Build Context for Debugging

```bash
curl -X POST "http://localhost:8000/ai/rag/kb/kb-12345/augment?query=reset+password&top_k=3" \
  -H "Authorization: Bearer TOKEN"
```

Response:
```json
{
  "status": "success",
  "context": "Retrieved 3 relevant documents:\n\n[Document 1: Account Management]\nContent: To reset your password...\n\n[Document 2: Security...]...",
  "source_documents": 3,
  "tokens_added": 1245
}
```

This is exactly what gets injected into the LLM prompt! ✅

---

## Troubleshooting

### Problem: No results when searching
**Solution**: Make sure documents are uploaded and indexed
```bash
curl -X GET "http://localhost:8000/ai/rag/kb/kb-12345/documents" \
  -H "Authorization: Bearer TOKEN"

# Check: is_indexed should be true, chunk_count > 0
```

### Problem: Agent not using RAG
**Solution**: Verify agent config includes KB ID
```bash
curl -X GET "http://localhost:8000/ai/agents/agent-xyz" \
  -H "Authorization: Bearer TOKEN"

# Check: config.rag_knowledge_base_id should be set
```

### Problem: Slow responses
**Solution**: Typical RAG adds 100-200ms. If slower:
1. Check database connection
2. Try fewer documents (top_k=3 vs top_k=20)
3. Verify pgvector indexes exist

---

## What's Happening Behind the Scenes

```
User Query: "How do I reset my password?"
                    ↓
    Agent receives task with this question
                    ↓
    RAG retrieves relevant docs (50ms)
                    ↓
    Context built: "[Document 1] To reset... [Document 2] Password..."
                    ↓
    Context + question combined into prompt
                    ↓
    LLM processes augmented prompt
                    ↓
    Response generated with RAG knowledge
                    ↓
    User gets accurate, sourced answer ✅
```

---

## Next: Production Deployment

### Checklist
- [ ] Create knowledge bases for your documentation
- [ ] Upload all product docs/guides/FAQs
- [ ] Create agents with RAG enabled
- [ ] Test end-to-end with real questions
- [ ] Configure rate limiting
- [ ] Set up monitoring/logging
- [ ] Test error scenarios
- [ ] Deploy to production

### Performance Tips
1. **Batch upload** documents during off-peak hours
2. **Monitor** search latency with `/ai/rag/kb/{kb_id}/search`
3. **Index size** — keep under 1000 documents per KB for best performance
4. **Update frequency** — re-index docs when content changes
5. **Cost** — ~$0.0001 per document indexed (with OpenAI embeddings)

---

## Need Help?

📖 **Full Documentation**: See `RAG_GUIDE.md`
🏗️ **Architecture**: See `RAG_IMPLEMENTATION.md`
💬 **Questions**: Review the API responses and logs

---

**That's it! You now have a knowledge-aware AI chatbot. 🚀**
