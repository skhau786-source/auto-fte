"""
Loadest load testing script for the Inventory Management API.

Usage:
    pip install locust httpx
    locust -f locustfile.py --host=http://localhost:8000 --users=100 --spawn-rate=10

Scenarios:
    - Browse products (light read)
    - Search and filter (medium read)
    - Create products (write)
    - Update inventory (write + Shopify sync)
    - Mixed workload (realistic user simulation)
"""

import random
import time
import uuid

from locust import HttpUser, task, between, constant


class InventoryBrowseUser(HttpUser):
    """
    Simulates a user browsing the inventory catalog.

    Mostly reads with occasional writes.
    Weight: 3 (3x more likely to be selected than CreateUser)
    """
    wait_time = between(1, 5)
    weight = 3

    @task(5)
    def list_products(self):
        self.client.get("/inventory?page=1&page_size=20", name="GET /inventory (page 1)")

    @task(3)
    def search_products(self):
        terms = ["test", "product", "shirt", "shoe", "widget", "gadget"]
        term = random.choice(terms)
        self.client.get(f"/inventory/search?search={term}", name="GET /inventory/search")

    @task(2)
    def view_product(self):
        # Since we don't know real product IDs, we accept any 404 as expected
        self.client.get(f"/inventory/{uuid.uuid4()}", name="GET /inventory/{id} (404)")

    @task(1)
    def low_stock(self):
        self.client.get("/inventory/low-stock", name="GET /inventory/low-stock")

    @task(1)
    def transaction_history(self):
        self.client.get("/inventory/history", name="GET /inventory/history")

    @task(1)
    def health_check(self):
        self.client.get("/health", name="GET /health")


class InventoryCreateUser(HttpUser):
    """
    Simulates users creating products and adjusting inventory.

    More write-heavy than BrowseUser.
    Weight: 1
    """
    wait_time = between(2, 8)
    weight = 1

    def on_start(self):
        """Create a few products to have inventory to work with."""
        for i in range(3):
            self.client.post(
                "/inventory",
                json={
                    "title": f"Load Test Product {time.time_ns()}",
                    "variants": [
                        {"title": "Default", "sku": f"LOAD-{time.time_ns()}-{i}", "price": 9.99, "inventory_quantity": 100},
                    ],
                },
                name="POST /inventory (warmup)",
            )

    @task(3)
    def create_product(self):
        sku = f"LOAD-{time.time_ns()}-{random.randint(1, 100000)}"
        self.client.post(
            "/inventory",
            json={
                "title": f"Load Test {random.choice(['Widget', 'Gadget', 'Tool', 'Part'])} {time.time_ns()}",
                "variants": [
                    {
                        "title": random.choice(["Red", "Blue", "Green", "Small", "Large"]),
                        "sku": sku,
                        "price": round(random.uniform(5.0, 500.0), 2),
                        "inventory_quantity": random.randint(0, 1000),
                    },
                ],
            },
            name="POST /inventory (create)",
        )

    @task(2)
    def update_stock(self):
        # Since we can't get real variant IDs from the API without a prior request,
        # we send a random UUID which will produce a 404 — this still measures
        # the request handling path
        self.client.post(
            "/inventory/update-stock",
            json={
                "variant_id": str(uuid.uuid4()),
                "quantity_change": random.choice([-5, -10, 10, 25, 50]),
            },
            name="POST /inventory/update-stock (404 expected)",
        )


class MixedUser(HttpUser):
    """
    Realistic mixed workload: 80% reads, 20% writes.
    Weight: 5 (most common user type)
    """
    wait_time = between(0.5, 3)
    weight = 5

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.product_count = 0

    @task(8)
    def read_operations(self):
        ops = [
            ("GET /inventory?page=1&page_size=20", lambda: self.client.get("/inventory?page=1&page_size=20")),
            ("GET /inventory/search", lambda: self.client.get(f"/inventory/search?search={random.choice(['a', 'e', 'i', 'o', 'u'])}")),
            ("GET /inventory/low-stock", lambda: self.client.get("/inventory/low-stock")),
            ("GET /inventory/history", lambda: self.client.get("/inventory/history")),
            ("GET /health", lambda: self.client.get("/health")),
        ]
        name, func = random.choice(ops)
        func()

    @task(2)
    def write_operations(self):
        ops = [
            ("POST /inventory (create)", lambda: self.client.post(
                "/inventory",
                json={
                    "title": f"Mixed Load {time.time_ns()}",
                    "variants": [{"title": "V1", "sku": f"MIX-{time.time_ns()}", "price": 14.99, "inventory_quantity": 50}],
                },
            )),
            ("POST /inventory/update-stock", lambda: self.client.post(
                "/inventory/update-stock",
                json={"variant_id": str(uuid.uuid4()), "quantity_change": random.choice([-5, 10])},
            )),
        ]
        name, func = random.choice(ops)
        func()
