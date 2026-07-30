"""
Performance Benchmark — Inventory Management Module

Measures latency for the most critical inventory operations:
1. Create product with variants
2. Update inventory (single adjustment)
3. Bulk adjustment (10 items)
4. List products (paginated)
5. Low stock detection
6. Transaction history

Usage:
    cd backend-fte
    python benchmark.py [--requests 100] [--concurrency 10]

Requires a running API server:
    docker compose up -d
    docker compose exec api alembic upgrade head
"""

import time
import statistics
import asyncio
import sys
from typing import Callable, Awaitable
from dataclasses import dataclass, field

import httpx

API_BASE = "http://localhost:8000"


@dataclass
class BenchmarkResult:
    name: str
    samples: list[float] = field(default_factory=list)

    @property
    def avg_ms(self) -> float:
        return statistics.mean(self.samples) * 1000 if self.samples else 0

    @property
    def p50_ms(self) -> float:
        return statistics.median(self.samples) * 1000 if self.samples else 0

    @property
    def p95_ms(self) -> float:
        if not self.samples:
            return 0
        sorted_s = sorted(self.samples)
        idx = int(len(sorted_s) * 0.95)
        return sorted_s[idx] * 1000

    @property
    def p99_ms(self) -> float:
        if not self.samples:
            return 0
        sorted_s = sorted(self.samples)
        idx = int(len(sorted_s) * 0.99)
        return sorted_s[idx] * 1000

    @property
    def min_ms(self) -> float:
        return min(self.samples) * 1000 if self.samples else 0

    @property
    def max_ms(self) -> float:
        return max(self.samples) * 1000 if self.samples else 0

    @property
    def ops_per_sec(self) -> float:
        total = sum(self.samples)
        return len(self.samples) / total if total > 0 else 0


async def benchmark_operation(
    name: str,
    func: Callable[[], Awaitable],
    requests: int = 50,
    warmup: int = 5,
) -> BenchmarkResult:
    """Benchmark a single operation with warmup and measurement phases."""
    result = BenchmarkResult(name=name)

    # Warmup
    for _ in range(warmup):
        try:
            await func()
        except Exception:
            pass

    # Measurement
    for _ in range(requests):
        start = time.time()
        try:
            await func()
        except Exception as exc:
            print(f"  ⚠️  {name}: error - {exc}")
            continue
        elapsed = time.time() - start
        result.samples.append(elapsed)

    return result


async def run_benchmarks(requests: int = 50):
    """Run all benchmarks against the API."""
    async with httpx.AsyncClient(base_url=API_BASE, timeout=30.0) as client:
        results = []

        # 1. Health check (baseline)
        async def health():
            resp = await client.get("/health")
            resp.raise_for_status()
        results.append(await benchmark_operation("GET /health", health, requests=min(requests, 20)))

        # 2. Create product with variants
        async def create_product():
            resp = await client.post(
                "/inventory",
                json={
                    "title": f"Benchmark Product {time.time_ns()}",
                    "variants": [
                        {"title": "V1", "sku": f"BENCH-SKU-{time.time_ns()}-1", "price": 19.99, "inventory_quantity": 100},
                        {"title": "V2", "sku": f"BENCH-SKU-{time.time_ns()}-2", "price": 29.99, "inventory_quantity": 50},
                    ],
                },
            )
            resp.raise_for_status()
        results.append(await benchmark_operation("POST /inventory (2 variants)", create_product, requests=min(requests, 30)))

        # 3. Get product list
        async def list_products():
            resp = await client.get("/inventory?page=1&page_size=20")
            resp.raise_for_status()
        results.append(await benchmark_operation("GET /inventory (list 20)", list_products, requests=requests))

        # 4. Search products
        async def search_products():
            resp = await client.get("/inventory/search?search=Benchmark")
            resp.raise_for_status()
        results.append(await benchmark_operation("GET /inventory/search", search_products, requests=requests))

        # 5. Get low stock
        async def low_stock():
            resp = await client.get("/inventory/low-stock")
            resp.raise_for_status()
        results.append(await benchmark_operation("GET /inventory/low-stock", low_stock, requests=requests))

        # 6. Get history
        async def get_history():
            resp = await client.get("/inventory/history")
            resp.raise_for_status()
        results.append(await benchmark_operation("GET /inventory/history", get_history, requests=requests))

        # Print results
        print("\n" + "=" * 90)
        print(f"{'Operation':<45} {'Avg(ms)':<10} {'P50(ms)':<10} {'P95(ms)':<10} {'P99(ms)':<10} {'Ops/s':<10}")
        print("=" * 90)
        for r in results:
            print(
                f"{r.name:<45} {r.avg_ms:<10.1f} {r.p50_ms:<10.1f} "
                f"{r.p95_ms:<10.1f} {r.p99_ms:<10.1f} {r.ops_per_sec:<10.1f}"
            )
        print("=" * 90)

        # Summary
        total_ops = sum(len(r.samples) for r in results)
        total_time = sum(sum(r.samples) for r in results)
        print(f"\nTotal operations: {total_ops}")
        print(f"Total time: {total_time:.2f}s")
        print(f"Overall throughput: {total_ops / total_time:.1f} ops/sec")
        print()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Inventory Module Benchmark")
    parser.add_argument("--requests", type=int, default=50, help="Number of requests per operation")
    args = parser.parse_args()

    print(f"\n🔬 Inventory Benchmark — {args.requests} requests per operation\n")
    asyncio.run(run_benchmarks(requests=args.requests))


if __name__ == "__main__":
    main()
