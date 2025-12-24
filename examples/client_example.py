"""
Example client demonstrating how to use the Clanker Web API.

Run the server first:
    uv run uvicorn examples.web_api:app --reload

Then run this script:
    uv run python examples/client_example.py
"""

import asyncio

import httpx


API_BASE = "http://localhost:8000"


async def main():
    async with httpx.AsyncClient() as client:
        print("🌐 Clanker Web API Client Demo\n")

        # 1. Health check
        print("1️⃣  Checking API health...")
        response = await client.get(f"{API_BASE}/")
        data = response.json()
        print(f"   ✅ Status: {data['status']}")
        print(f"   📦 Providers: LLM={data['providers']['llm']}, TTS={data['providers']['tts']}")
        print(f"   🎭 Personas available: {', '.join(data['personas'])}\n")

        # 2. List templates
        print("2️⃣  Fetching shitpost templates...")
        response = await client.get(f"{API_BASE}/templates")
        data = response.json()
        print(f"   📝 Found {data['count']} templates")
        print(f"   🏷️  Categories: {', '.join(data['categories'])}")
        print(f"   📋 First template: {data['templates'][0]['name']} - {data['templates'][0]['description']}\n")

        # 3. Generate a shitpost
        print("3️⃣  Generating a shitpost...")
        response = await client.post(
            f"{API_BASE}/shitpost",
            json={
                "user_id": "demo_user_123",
                "category": "roast",
                "variables": {"target": "JavaScript"},
            },
        )
        data = response.json()
        print(f"   💩 Shitpost: {data['shitpost']}")
        print(f"   📄 Template used: {data['template_used']}\n")

        # 4. Chat with default persona
        print("4️⃣  Chatting with default persona...")
        response = await client.post(
            f"{API_BASE}/chat",
            json={
                "message": "What's the best programming language?",
                "user_id": "demo_user_123",
                "session_id": "demo_session_456",
                "persona_name": "default",
            },
        )
        data = response.json()
        print(f"   💬 Reply: {data['reply']}\n")

        # 5. Generate another shitpost with different category
        print("5️⃣  Generating an advice shitpost...")
        response = await client.post(
            f"{API_BASE}/shitpost",
            json={
                "user_id": "demo_user_123",
                "category": "advice",
            },
        )
        data = response.json()
        print(f"   💡 Advice: {data['shitpost']}")
        print(f"   📄 Template used: {data['template_used']}\n")

        print("✅ Demo complete!")
        print("\n💡 Try it yourself:")
        print("   - Visit http://localhost:8000/docs for interactive API docs")
        print("   - Use curl to make custom requests (see examples/README.md)")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except httpx.ConnectError:
        print("❌ Error: Could not connect to API server.")
        print("   Make sure the server is running:")
        print("   uv run uvicorn examples.web_api:app --reload")
