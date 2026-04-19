import asyncio
from httpx import AsyncClient
from database import async_session, Goal

async def main():
    async with async_session() as db:
        res = await db.execute("SELECT id FROM goals ORDER BY created_at DESC LIMIT 1;")
        goal_id = res.scalar()
        if not goal_id:
            print("No goals")
            return
        print(f"Latest Goal ID: {goal_id}")
        
        # Now try to hit the API, bypassing auth by just calling the route function directly
        from api.goals import get_goal
        try:
            goal_data = await get_goal(goal_id, db, {"sub": "123"})
            print("Successfully retrieved goal.")
        except Exception as e:
            print(f"Error calling get_goal: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
