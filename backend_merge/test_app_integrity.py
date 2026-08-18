import os
import sys
import py_compile
import glob

print("==========================================")
print("1. VERIFYING SYNTAX OF ALL PYTHON FILES")
print("==========================================")

py_files = glob.glob("app/**/*.py", recursive=True) + ["migrate_db.py"]
errors = []

for py_file in py_files:
    try:
        py_compile.compile(py_file, doraise=True)
        print(f"  [OK] {py_file}")
    except py_compile.PyCompileError as e:
        print(f"  [FAIL] {py_file}: {e}")
        errors.append(py_file)

if errors:
    print(f"\nSYNTAX ERRORS FOUND IN {len(errors)} FILES!")
    sys.exit(1)
else:
    print("\nAll Python files compiled cleanly with 0 syntax errors.")

print("\n==========================================")
print("2. VERIFYING IMPORTS AND FASTAPI ROUTER MAP")
print("==========================================")

# Mock database engine to allow loading app even without active DB server
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

try:
    from app.config import settings
    print(f"  [OK] Config loaded. App Name: '{settings.APP_NAME}', ENV: '{settings.ENV}'")
    
    from app.database import Base
    from app.models import User, GeneratedPost, InstagramAccount, ShopifyStore, WooCommerceStore, Product, WooCommerceProduct, LoginLog

    tables = list(Base.metadata.tables.keys())
    print(f"  [OK] SQLAlchemy Models loaded successfully. Defined tables: {tables}")
    
    from app.schemas import GeneratePostRequest, GeneratedPostOut, InstagramAccountOut, PublishPostRequest, PublishPostResponse
    print(f"  [OK] Pydantic Schemas imported successfully.")

    from app.services import ai_post_service, instagram_service, auth_service
    print(f"  [OK] Business Logic Services imported successfully.")

    from app.main import app
    print(f"  [OK] FastAPI app loaded successfully.")

    print("\n  Mounted Endpoints:")
    for route in app.routes:
        methods = getattr(route, 'methods', None)
        path = getattr(route, 'path', None)
        name = getattr(route, 'name', '')
        if path:
            print(f"    - {list(methods) if methods else 'MOUNT'} {path} [{name}]")

    print("\n==========================================")
    print("ALL IMPORT & STRUCTURE CHECKS PASSED CLEANLY!")
    print("==========================================")


except Exception as e:
    import traceback
    print(f"\n[ERROR] Import / runtime initialization failed:")
    traceback.print_exc()
    sys.exit(1)
