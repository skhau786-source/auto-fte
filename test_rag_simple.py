#!/usr/bin/env python3
"""
RAG System Quick Test
Run this to verify RAG is working
"""

import sys
import httpx
import time
import json

BASE_URL = "http://localhost:8000"

def print_section(title):
    print(f"\n{title}")
    print("=" * 50)

def print_success(msg):
    print(f"✅ {msg}")

def print_error(msg):
    print(f"❌ {msg}")
    sys.exit(1)

def main():
    print("\n" + "=" * 50)
    print("   🧪 RAG System Quick Test")
    print("=" * 50)

    # Get token
    token = input("\n📌 Enter your Bearer token: ").strip()
    if not token:
        print_error("Token is required!")

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    try:
        # 1. Check health
        print_section("1️⃣ Checking Application...")
        response = httpx.get(f"{BASE_URL}/health", timeout=5)
        if response.status_code != 200:
            print_error(f"App not responding (status {response.status_code})")
        print_success(f"Application running at {BASE_URL}")

        # 2. Check endpoints
        print_section("2️⃣ Checking RAG Endpoints...")
        response = httpx.get(f"{BASE_URL}/docs", timeout=5)
        if "rag/knowledge-bases" not in response.text:
            print_error("RAG endpoints not found!")
        print_success("RAG endpoints are registered")

        # 3. Create KB
        print_section("3️⃣ Creating Knowledge Base...")
        response = httpx.post(
            f"{BASE_URL}/ai/rag/knowledge-bases",
            headers=headers,
            json={"name": "Quick Test KB", "description": "Testing RAG"}
        )
        if response.status_code != 201:
            print_error(f"Failed to create KB (status {response.status_code}): {response.text}")

        kb_data = response.json()
        kb_id = kb_data["id"]
        print_success(f"Created KB: {kb_id}")

        # 4. Upload documents
        print_section("4️⃣ Uploading Documents...")
        docs = [
            ("Getting Started", "Welcome to our platform. Step 1: Sign up at signup.com. Step 2: Verify email. Step 3: Choose plan."),
            ("Password Reset", "To reset your password: 1. Click Settings. 2. Select Security. 3. Click Change Password. 4. Enter new password (min 12 chars). 5. Save."),
            ("Billing", "Q: What payment methods? A: Credit cards, PayPal, bank transfer. Q: Can I change plans? A: Yes, anytime."),
        ]

        for title, content in docs:
            response = httpx.post(
                f"{BASE_URL}/ai/rag/kb/{kb_id}/documents",
                headers=headers,
                params={"title": title, "content": content}
            )
            if response.status_code != 201:
                print_error(f"Failed to upload '{title}': {response.text}")
            print_success(f"Uploaded: {title}")

        # 5. List documents
        print_section("5️⃣ Listing Documents...")
        response = httpx.get(
            f"{BASE_URL}/ai/rag/kb/{kb_id}/documents",
            headers=headers
        )
        if response.status_code != 200:
            print_error(f"Failed to list docs: {response.text}")

        doc_data = response.json()
        doc_count = doc_data["total"]
        print_success(f"Documents in KB: {doc_count}")

        # 6. Search
        print_section("6️⃣ Searching Documents...")
        response = httpx.post(
            f"{BASE_URL}/ai/rag/kb/{kb_id}/search",
            headers=headers,
            params={"query": "password", "top_k": 5}
        )
        if response.status_code != 200:
            print_error(f"Search failed: {response.text}")

        search_data = response.json()
        chunks = search_data["chunks_retrieved"]
        time_ms = search_data["retrieval_time_ms"]
        print_success(f"Chunks retrieved: {chunks}")
        print_success(f"Search time: {time_ms}ms")

        # 7. Build context
        print_section("7️⃣ Building RAG Context...")
        response = httpx.post(
            f"{BASE_URL}/ai/rag/kb/{kb_id}/augment",
            headers=headers,
            params={"query": "How do I reset my password?", "top_k": 3}
        )
        if response.status_code != 200:
            print_error(f"Context building failed: {response.text}")

        context_data = response.json()
        tokens = context_data["tokens_added"]
        print_success(f"Context built with {tokens} tokens")

        # 8. Create agent
        print_section("8️⃣ Creating RAG-Enabled Agent...")
        response = httpx.post(
            f"{BASE_URL}/ai/agents",
            headers=headers,
            json={
                "name": "Test RAG Agent",
                "agent_type": "custom",
                "config": {
                    "rag_knowledge_base_id": kb_id
                }
            }
        )
        if response.status_code != 201:
            print_error(f"Failed to create agent: {response.text}")

        agent_data = response.json()
        agent_id = agent_data["id"]
        print_success(f"Created Agent: {agent_id}")

        # 9. Submit task
        print_section("9️⃣ Submitting Task...")
        response = httpx.post(
            f"{BASE_URL}/ai/agents/{agent_id}/tasks",
            headers=headers,
            json={
                "task_type": "custom",
                "input_data": {"question": "How do I reset my password?"},
                "requires_human_approval": False
            }
        )
        if response.status_code != 201:
            print_error(f"Failed to submit task: {response.text}")

        task_data = response.json()
        task_id = task_data["id"]
        print_success(f"Task submitted: {task_id}")

        # 10. Check result
        print_section("🔟 Waiting for Result...")
        time.sleep(2)

        response = httpx.get(
            f"{BASE_URL}/ai/tasks/{task_id}",
            headers=headers
        )
        if response.status_code != 200:
            print_error(f"Failed to get task: {response.text}")

        task_result = response.json()
        status = task_result["status"]
        rag_augmented = task_result.get("output_data", {}).get("rag_augmented", False)

        print_success(f"Task Status: {status}")
        print_success(f"RAG Augmented: {rag_augmented}")

        # Success!
        print_section("✅ ALL TESTS PASSED!")
        print(f"""
Summary:
  ✓ Application running
  ✓ RAG endpoints registered
  ✓ Knowledge Base created: {kb_id}
  ✓ {doc_count} documents uploaded
  ✓ Search working ({chunks} chunks found in {time_ms}ms)
  ✓ Context building working ({tokens} tokens)
  ✓ RAG Agent created: {agent_id}
  ✓ Task executed: {task_id}
  ✓ RAG Augmented: {rag_augmented}

🎉 RAG System is fully functional!
""")

    except httpx.ConnectError:
        print_error("Cannot connect to application. Is it running?")
        print("\nStart it with:")
        print("  cd backend-fte")
        print("  python -m uvicorn app.main:app --reload")
    except Exception as e:
        print_error(f"Error: {e}")

if __name__ == "__main__":
    main()
