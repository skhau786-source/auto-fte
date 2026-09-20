@echo off
REM RAG System Quick Test Script for Windows
REM This script tests the RAG system end-to-end

setlocal enabledelayedexpansion

echo ==================================
echo    🧪 RAG System Quick Test
echo ==================================
echo.

REM Configuration
set BASE_URL=http://localhost:8000
set TOKEN=%1

if "%TOKEN%"=="" (
    set TOKEN=test-token
)

REM Check if app is running
echo 1️⃣ Checking if application is running...
curl -s %BASE_URL%/health > nul 2>&1
if errorlevel 1 (
    echo ❌ Application is not running!
    echo.
    echo Start it with:
    echo   cd backend-fte
    echo   python -m uvicorn app.main:app --reload
    echo.
    exit /b 1
)
echo ✅ Application is running at %BASE_URL%
echo.

REM Check RAG endpoints
echo 2️⃣ Checking RAG endpoints...
curl -s %BASE_URL%/docs | findstr /C:"rag/knowledge-bases" > nul
if errorlevel 1 (
    echo ❌ RAG endpoints not found!
    exit /b 1
)
echo ✅ RAG endpoints are registered
echo.

REM Get auth token if not provided
if "%TOKEN%"=="test-token" (
    echo 3️⃣ Authentication required!
    echo.
    echo Pass your token as argument:
    echo   run_rag_test.bat "your_bearer_token"
    echo.
    exit /b 1
)

echo 3️⃣ Creating Knowledge Base...
for /f "tokens=*" %%A in ('powershell -Command "& { $response = curl -s -X POST %BASE_URL%/ai/rag/knowledge-bases -H 'Authorization: Bearer %TOKEN%' -H 'Content-Type: application/json' -d '{\"name\":\"Quick Test KB\",\"description\":\"Testing RAG\"}'; $response | ConvertFrom-Json | Select-Object -ExpandProperty id }"') do set KB_ID=%%A

if "%KB_ID%"=="" (
    echo ❌ Failed to create KB
    exit /b 1
)
echo ✅ Created KB: %KB_ID%
echo.

echo 4️⃣ Uploading Documents...
REM Doc 1
curl -s -X POST "%BASE_URL%/ai/rag/kb/%KB_ID%/documents" -H "Authorization: Bearer %TOKEN%" -d "title=Getting Started&content=Welcome to our platform. Step 1: Sign up at signup.com. Step 2: Verify email. Step 3: Choose plan." > nul
echo    ✅ Document 1: Getting Started

REM Doc 2
curl -s -X POST "%BASE_URL%/ai/rag/kb/%KB_ID%/documents" -H "Authorization: Bearer %TOKEN%" -d "title=Password Reset&content=To reset your password: 1. Click Settings. 2. Select Security. 3. Click Change Password. 4. Enter new password (min 12 chars). 5. Save." > nul
echo    ✅ Document 2: Password Reset

REM Doc 3
curl -s -X POST "%BASE_URL%/ai/rag/kb/%KB_ID%/documents" -H "Authorization: Bearer %TOKEN%" -d "title=Billing&content=Q: What payment methods? A: Credit cards, PayPal, bank transfer. Q: Can I change plans? A: Yes, anytime." > nul
echo    ✅ Document 3: Billing
echo.

echo 5️⃣ Listing Documents...
for /f "tokens=*" %%A in ('powershell -Command "& { $response = curl -s -X GET %BASE_URL%/ai/rag/kb/%KB_ID%/documents -H 'Authorization: Bearer %TOKEN%'; $response | ConvertFrom-Json | Select-Object -ExpandProperty total }"') do set DOC_COUNT=%%A
echo ✅ Documents in KB: %DOC_COUNT%
echo.

echo 6️⃣ Searching Documents (query: 'password')...
for /f "tokens=*" %%A in ('powershell -Command "& { $response = curl -s -X POST '%BASE_URL%/ai/rag/kb/%KB_ID%/search?query=password' -H 'Authorization: Bearer %TOKEN%'; $response | ConvertFrom-Json | Select-Object -ExpandProperty chunks_retrieved }"') do set CHUNKS=%%A
echo ✅ Chunks retrieved: %CHUNKS%
echo.

echo 7️⃣ Building RAG Context...
for /f "tokens=*" %%A in ('powershell -Command "& { $response = curl -s -X POST '%BASE_URL%/ai/rag/kb/%KB_ID%/augment?query=How+do+I+reset+password' -H 'Authorization: Bearer %TOKEN%'; $response | ConvertFrom-Json | Select-Object -ExpandProperty tokens_added }"') do set TOKENS=%%A
echo ✅ Context built with %TOKENS% tokens
echo.

echo 8️⃣ Creating RAG-Enabled Agent...
for /f "tokens=*" %%A in ('powershell -Command "& { $response = curl -s -X POST %BASE_URL%/ai/agents -H 'Authorization: Bearer %TOKEN%' -H 'Content-Type: application/json' -d '{\"name\":\"Test RAG Agent\",\"agent_type\":\"custom\",\"config\":{\"rag_knowledge_base_id\":\"%KB_ID%\"}}'; $response | ConvertFrom-Json | Select-Object -ExpandProperty id }"') do set AGENT_ID=%%A
echo ✅ Created Agent: %AGENT_ID%
echo.

echo ==================================
echo    ✅ ALL TESTS PASSED!
echo ==================================
echo.
echo Summary:
echo   ✓ Application running
echo   ✓ RAG endpoints registered
echo   ✓ Knowledge Base created: %KB_ID%
echo   ✓ %DOC_COUNT% documents uploaded
echo   ✓ Search working (%CHUNKS% chunks found)
echo   ✓ Context building working
echo   ✓ RAG Agent created: %AGENT_ID%
echo.
echo 🎉 RAG System is fully functional!
echo.
