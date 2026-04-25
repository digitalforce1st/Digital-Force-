"""
Test the live API — login and list accounts.
"""
import asyncio
import httpx

BASE = "http://localhost:8000"

async def main():
    async with httpx.AsyncClient() as client:
        # Try to login
        print("=== LOGIN ===")
        r = await client.post(f"{BASE}/api/auth/login", json={
            "username": "admin",
            "password": "admin"
        })
        print(f"  Status: {r.status_code}")
        if r.status_code != 200:
            # try email
            r = await client.post(f"{BASE}/api/auth/login", json={
                "username": "digitalforce1st@gmail.com",
                "password": "admin"
            })
            print(f"  Status (email): {r.status_code}")
        
        if r.status_code == 200:
            token = r.json().get("access_token")
            print(f"  Token obtained: {token[:30]}...")
        
            print("\n=== GET /api/accounts ===")
            r2 = await client.get(f"{BASE}/api/accounts", headers={"Authorization": f"Bearer {token}"})
            print(f"  Status: {r2.status_code}")
            print(f"  Response: {r2.text[:2000]}")
        else:
            print(f"  Login failed: {r.text}")
            
            # Try health check
            h = await client.get(f"{BASE}/api/health")
            print(f"\n=== HEALTH: {h.status_code} ===")
            print(h.text[:500])

asyncio.run(main())
