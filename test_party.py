"""Test Party mode con diversi formati di expiration."""
import asyncio
import aiohttp
import json
import sys
from datetime import datetime, timedelta

API_BASE_URL = "https://portal.planetsmartcity.com/api/v3/"
API_ENDPOINT = "sensors_data_request"

def headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "x-planet-source": "mobile",
        "timezone-offset": "-60",
        "Content-Type": "application/json",
    }

async def api_post(session: aiohttp.ClientSession, token: str, payload: dict, label: str = "") -> dict:
    url = f"{API_BASE_URL}{API_ENDPOINT}"
    print(f"\n{'='*60}")
    print(f"🔬 {label}")
    print(f"{'='*60}")
    print(f"📤 REQUEST: {json.dumps(payload, indent=2)}")
    async with session.post(url, json=payload, headers=headers(token)) as resp:
        print(f"📊 STATUS: {resp.status}")
        data = await resp.json(content_type=None)
        print(f"📥 RESPONSE: {json.dumps(data, indent=2)[:1000]}")
        return {"status": resp.status, "data": data}

async def test_party(token: str):
    async with aiohttp.ClientSession() as session:
        # Get current state
        result = await api_post(session, token, {"request_type": "full_bo"}, "GET STATE")
        thermostat = result["data"][0] if isinstance(result["data"], list) else result["data"]
        unit_code = thermostat.get("unitCode")
        category = thermostat.get("category")
        
        # Restore function
        restore_auto = {
            "request_type": "post_bo_setpoint",
            "unitCode": unit_code,
            "category": category,
            "zones": [
                {"id": "1", "mode": "auto", "expiration": 0},
                {"id": "2", "mode": "auto", "expiration": 0},
                {"id": "3", "mode": "auto", "expiration": 0},
            ]
        }
        
        print("\n" + "🎉"*30)
        print("TEST PARTY MODE - Diversi formati expiration")
        print("🎉"*30)
        
        # TEST 1: expiration = 1 (1 ora come da manuale)
        await asyncio.sleep(0.5)
        r1 = await api_post(session, token, {
            "request_type": "post_bo_setpoint",
            "unitCode": unit_code,
            "category": category,
            "zones": [{"id": "1", "mode": "party", "expiration": 1}]
        }, "TEST 1: Party expiration=1 (1 ora)")
        
        if r1["status"] == 200 and r1["data"] and r1["data"][0].get("success"):
            print("\n✅ expiration=1 FUNZIONA! Verifico stato...")
            await asyncio.sleep(1)
            check = await api_post(session, token, {"request_type": "full_bo"}, "CHECK STATE after party")
            if check["data"]:
                t = check["data"][0] if isinstance(check["data"], list) else check["data"]
                z1 = t["zones"][0]
                print(f"\n📍 Zone 1 dopo Party:")
                print(f"   mode: {z1.get('mode')}")
                print(f"   expiration: {z1.get('expiration')}")
                print(f"   dateExpiration: {z1.get('dateExpiration')}")
        
        # Restore
        await asyncio.sleep(0.5)
        await api_post(session, token, restore_auto, "RESTORE AUTO")
        await asyncio.sleep(0.5)
        
        # TEST 2: expiration = 2 (2 ore)
        r2 = await api_post(session, token, {
            "request_type": "post_bo_setpoint",
            "unitCode": unit_code,
            "category": category,
            "zones": [{"id": "1", "mode": "party", "expiration": 2}]
        }, "TEST 2: Party expiration=2 (2 ore)")
        
        if r2["status"] == 200 and r2["data"] and r2["data"][0].get("success"):
            print("\n✅ expiration=2 FUNZIONA!")
            await asyncio.sleep(1)
            check = await api_post(session, token, {"request_type": "full_bo"}, "CHECK STATE")
            if check["data"]:
                t = check["data"][0] if isinstance(check["data"], list) else check["data"]
                z1 = t["zones"][0]
                print(f"\n📍 Zone 1 dopo Party 2h:")
                print(f"   mode: {z1.get('mode')}")
                print(f"   expiration: {z1.get('expiration')}")
                print(f"   dateExpiration: {z1.get('dateExpiration')}")
        
        # Restore
        await asyncio.sleep(0.5)
        await api_post(session, token, restore_auto, "RESTORE AUTO")
        await asyncio.sleep(0.5)
        
        # TEST 3: expiration = 60 (60 minuti?)
        r3 = await api_post(session, token, {
            "request_type": "post_bo_setpoint",
            "unitCode": unit_code,
            "category": category,
            "zones": [{"id": "1", "mode": "party", "expiration": 60}]
        }, "TEST 3: Party expiration=60 (60 minuti?)")
        
        if r3["status"] == 200 and r3["data"] and r3["data"][0].get("success"):
            print("\n✅ expiration=60 FUNZIONA!")
            await asyncio.sleep(1)
            check = await api_post(session, token, {"request_type": "full_bo"}, "CHECK STATE")
            if check["data"]:
                t = check["data"][0] if isinstance(check["data"], list) else check["data"]
                z1 = t["zones"][0]
                print(f"\n📍 Zone 1:")
                print(f"   mode: {z1.get('mode')}")
                print(f"   expiration: {z1.get('expiration')}")
                print(f"   dateExpiration: {z1.get('dateExpiration')}")
        
        # Restore
        await asyncio.sleep(0.5)
        await api_post(session, token, restore_auto, "RESTORE AUTO")
        
        # TEST 4: expiration in minuti (120 = 2 ore)
        await asyncio.sleep(0.5)
        r4 = await api_post(session, token, {
            "request_type": "post_bo_setpoint",
            "unitCode": unit_code,
            "category": category,
            "zones": [{"id": "1", "mode": "party", "expiration": 120}]
        }, "TEST 4: Party expiration=120 (120 minuti = 2h)")
        
        if r4["status"] == 200 and r4["data"] and r4["data"][0].get("success"):
            print("\n✅ expiration=120 FUNZIONA!")
            await asyncio.sleep(1)
            check = await api_post(session, token, {"request_type": "full_bo"}, "CHECK STATE")
            if check["data"]:
                t = check["data"][0] if isinstance(check["data"], list) else check["data"]
                z1 = t["zones"][0]
                print(f"\n📍 Zone 1:")
                print(f"   mode: {z1.get('mode')}")
                print(f"   expiration: {z1.get('expiration')} (minuti rimanenti?)")
                print(f"   dateExpiration: {z1.get('dateExpiration')}")
        
        # Final restore
        await asyncio.sleep(0.5)
        await api_post(session, token, restore_auto, "FINAL RESTORE AUTO")
        
        print("\n" + "="*60)
        print("✅ TEST COMPLETATI")
        print("="*60)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_party.py <ACCESS_TOKEN>")
        sys.exit(1)
    asyncio.run(test_party(sys.argv[1]))
