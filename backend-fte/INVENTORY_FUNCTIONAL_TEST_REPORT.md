# Inventory Management Functional Test Report

**Date:** 2026-07-23 19:13:58 UTC
**Target:** http://localhost:8000
**Overall Result:** SOME TESTS FAILED
**Passed:** 29/35
**Failed:** 6/35

## Executive Summary

| Category | Tests | Passed | Failed |
|----------|-------|--------|--------|
| PASS Admin | 4 | 4 | 0 |
| FAIL Auth | 2 | 0 | 2 |
| PASS Basic | 4 | 4 | 0 |
| PASS Dashboard | 1 | 1 | 0 |
| FAIL Errors | 5 | 4 | 1 |
| PASS Export | 7 | 7 | 0 |
| FAIL Inventory | 4 | 2 | 2 |
| FAIL Products | 5 | 4 | 1 |
| PASS Webhooks | 3 | 3 | 0 |

**Total** | **35** | **29** | **6** |


## Detailed Test Results

### PASS Basic: GET /health
- **Expected Status:** 200
- **Actual Status:** 200
- **Notes:** Health check

### PASS Basic: GET /ready
- **Expected Status:** [200, 503]
- **Actual Status:** 200
- **Notes:** Readiness check

### PASS Basic: GET /live
- **Expected Status:** 200
- **Actual Status:** 200
- **Notes:** Liveness check

### PASS Basic: GET /version
- **Expected Status:** 200
- **Actual Status:** 200
- **Notes:** Version info

### FAIL Auth: POST /auth/signup
- **Expected Status:** 201
- **Actual Status:** 500
- **Notes:** Create a new user
- **Request:** ```json
{
  "username": "testuser_1784834035",
  "email": "testuser_1784834035@test.com",
  "password": "TestPass123!",
  "full_name": "Test User"
}
```
- **Response Detail:** Internal server error

### FAIL Auth: POST /auth/login
- **Expected Status:** 200
- **Actual Status:** 401
- **Notes:** Login and get JWT
- **Request:** ```json
{
  "email": "testuser_1784834035@test.com",
  "password": "TestPass123!"
}
```
- **Response Detail:** Invalid credentials

### FAIL Products: POST POST /inventory
- **Expected Status:** 201
- **Actual Status:** 500
- **Notes:** Create product with variant
- **Request:** ```json
{
  "title": "Test Product 1784834036",
  "description": "A comprehensive test product",
  "vendor": "TestVendor",
  "product_type": "Physical",
  "status": "active",
  "category_id": "54085e6b-0165-4515-a2c1-546576e2046a",
  "featured_image_url": "https://example.com/image.png",
  "variants": [
    {
      "title": "Default",
      "sku": "SKU-1784834036",
      "barcode": "1234567890123",
      "price": "29.99",
      "compare_at_price": "39.99",
      "inventory_quantity": 100,
      "requires_shipping": true,
      "low_stock_threshold": 10
    }
  ]
}
```
- **Response Detail:** Internal server error

### PASS Products: GET GET /inventory
- **Expected Status:** 200
- **Actual Status:** 200
- **Notes:** List products

### PASS Products: GET GET /inventory/{id}
- **Expected Status:** 200
- **Actual Status:** 200
- **Notes:** Get single product
- **Request:** ```json
{
  "path_id": "ee6979ff-f954-4847-9300-a017f23fe228"
}
```

### PASS Products: GET GET /inventory/search
- **Expected Status:** 200
- **Actual Status:** 200
- **Notes:** Search products

### PASS Products: PUT PUT /inventory/{id}
- **Expected Status:** 200
- **Actual Status:** 200
- **Notes:** Update product
- **Request:** ```json
{
  "title": "Updated Product 1784834037",
  "vendor": "UpdatedVendor"
}
```

### PASS Inventory: POST POST /inventory/update-stock (+25)
- **Expected Status:** 200
- **Actual Status:** 200
- **Notes:** Adjust inventory (add stock)
- **Request:** ```json
{
  "variant_id": "b473f413-1f08-43dc-b390-2ad7ada4a08f",
  "quantity_change": 25,
  "reason": "Restock for testing"
}
```

### PASS Inventory: POST POST /inventory/update-stock (-10)
- **Expected Status:** 200
- **Actual Status:** 200
- **Notes:** Adjust inventory (remove stock)
- **Request:** ```json
{
  "variant_id": "b473f413-1f08-43dc-b390-2ad7ada4a08f",
  "quantity_change": -10,
  "reason": "Sale deduction"
}
```

### FAIL Inventory: GET GET /inventory/low-stock
- **Expected Status:** 200
- **Actual Status:** 422
- **Notes:** Get low stock items
- **Response Detail:** [{'type': 'uuid_parsing', 'loc': ['path', 'product_id'], 'msg': 'Input should be a valid UUID, invalid character: found `l` at 1', 'input': 'low-stock', 'ctx': {'error': 'invalid character: found `l` at 1'}}]

### FAIL Inventory: GET GET /inventory/history
- **Expected Status:** 200
- **Actual Status:** 422
- **Notes:** Get transaction history
- **Response Detail:** [{'type': 'uuid_parsing', 'loc': ['path', 'product_id'], 'msg': 'Input should be a valid UUID, invalid character: found `h` at 1', 'input': 'history', 'ctx': {'error': 'invalid character: found `h` at 1'}}]

### PASS Webhooks: POST POST /webhooks/inventory-levels-update
- **Expected Status:** 401
- **Actual Status:** 401
- **Notes:** Webhook rejected without HMAC
- **Request:** ```json
{
  "note": "No HMAC header"
}
```

### PASS Webhooks: POST POST /webhooks/products-update
- **Expected Status:** 401
- **Actual Status:** 401
- **Notes:** Webhook rejected without HMAC
- **Request:** ```json
{
  "note": "No HMAC header"
}
```

### PASS Webhooks: POST POST /webhooks/app-uninstalled
- **Expected Status:** 401
- **Actual Status:** 401
- **Notes:** Webhook rejected without HMAC
- **Request:** ```json
{
  "note": "No HMAC header"
}
```

### PASS Admin: GET GET /admin/stats
- **Expected Status:** [200, 404]
- **Actual Status:** 404
- **Notes:** Admin stats - may require store

### PASS Admin: GET GET /admin/queue/status
- **Expected Status:** [200, 404]
- **Actual Status:** 404
- **Notes:** Queue status - may require store

### PASS Admin: GET GET /admin/queue/dead-letters
- **Expected Status:** [200, 404]
- **Actual Status:** 404
- **Notes:** Dead letters - may require store

### PASS Admin: POST POST /admin/cache/flush
- **Expected Status:** [200, 404]
- **Actual Status:** 404
- **Notes:** Cache flush - may require store

### PASS Export: GET GET /export/products
- **Expected Status:** [200, 401, 404]
- **Actual Status:** 404
- **Notes:** 

### PASS Export: GET GET /export/products?format=csv
- **Expected Status:** [200, 401, 404]
- **Actual Status:** 404
- **Notes:** 

### PASS Export: GET GET /export/products?format=xlsx
- **Expected Status:** [200, 401, 404]
- **Actual Status:** 404
- **Notes:** 

### PASS Export: GET GET /export/transactions
- **Expected Status:** [200, 401, 404]
- **Actual Status:** 404
- **Notes:** 

### PASS Export: GET GET /export/transactions?format=csv
- **Expected Status:** [200, 401, 404]
- **Actual Status:** 404
- **Notes:** 

### PASS Export: GET GET /export/logs
- **Expected Status:** [200, 401, 404]
- **Actual Status:** 404
- **Notes:** 

### PASS Export: GET GET /export/logs?format=csv
- **Expected Status:** [200, 401, 404]
- **Actual Status:** 404
- **Notes:** 

### PASS Errors: GET GET /inventory/{nonexistent}
- **Expected Status:** [404, 401]
- **Actual Status:** 404
- **Notes:** Non-existent product

### PASS Errors: GET GET /inventory (no auth)
- **Expected Status:** 401
- **Actual Status:** 401
- **Notes:** Protected endpoint without auth

### PASS Errors: POST POST /inventory/update-stock (zero change)
- **Expected Status:** 422
- **Actual Status:** 422
- **Notes:** Zero quantity change returns 422
- **Request:** ```json
{
  "variant_id": "b37e2fe2-aea8-41e5-8983-847e6446c91d",
  "quantity_change": 0
}
```

### PASS Errors: POST POST /auth/signup (weak password)
- **Expected Status:** 422
- **Actual Status:** 422
- **Notes:** Weak password rejected
- **Request:** ```json
{
  "username": "bad",
  "email": "bad@test.com",
  "password": "short"
}
```

### FAIL Errors: GET GET /export/products?format=invalid
- **Expected Status:** [400, 422]
- **Actual Status:** 404
- **Notes:** Invalid format returns error
- **Response Detail:** Not Found

### PASS Dashboard: GET GET /metrics
- **Expected Status:** 200
- **Actual Status:** 200
- **Notes:** Prometheus metrics endpoint


## Bugs Found

### Bug: Auth - /auth/signup
- **Expected:** 201
- **Actual:** 500
- **Response Detail:** Internal server error

  - **Root Cause:** Likely a database connection issue, missing dependency, or unhandled exception
  - **Recommended Fix:** Check server logs for the full traceback

### Bug: Auth - /auth/login
- **Expected:** 200
- **Actual:** 401
- **Response Detail:** Invalid credentials

  - **Root Cause:** Authentication failure or missing/invalid token
  - **Recommended Fix:** Ensure JWT token is valid and included in Authorization header

### Bug: Products - POST /inventory
- **Expected:** 201
- **Actual:** 500
- **Response Detail:** Internal server error

  - **Root Cause:** Likely a database connection issue, missing dependency, or unhandled exception
  - **Recommended Fix:** Check server logs for the full traceback

### Bug: Inventory - GET /inventory/low-stock
- **Expected:** 200
- **Actual:** 422
- **Response Detail:** [{'type': 'uuid_parsing', 'loc': ['path', 'product_id'], 'msg': 'Input should be a valid UUID, invalid character: found `l` at 1', 'input': 'low-stock', 'ctx': {'error': 'invalid character: found `l` at 1'}}]

  - **Root Cause:** Request validation failed - check field requirements vs schema
  - **Recommended Fix:** Adjust payload to match Pydantic schema requirements

### Bug: Inventory - GET /inventory/history
- **Expected:** 200
- **Actual:** 422
- **Response Detail:** [{'type': 'uuid_parsing', 'loc': ['path', 'product_id'], 'msg': 'Input should be a valid UUID, invalid character: found `h` at 1', 'input': 'history', 'ctx': {'error': 'invalid character: found `h` at 1'}}]

  - **Root Cause:** Request validation failed - check field requirements vs schema
  - **Recommended Fix:** Adjust payload to match Pydantic schema requirements

### Bug: Errors - GET /export/products?format=invalid
- **Expected:** [400, 422]
- **Actual:** 404
- **Response Detail:** Not Found

  - **Root Cause:** Resource not found or endpoint requires a store to exist
  - **Recommended Fix:** Ensure prerequisites (e.g., store) exist before calling endpoint
