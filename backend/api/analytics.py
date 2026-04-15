"""
Digital Force — Analytics API
Aggregates real-time KPIs from the database for the analytics dashboard.
"""

import logging
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc

from database import (
    get_db, Goal, AgentTask, AgentLog,
    MediaAsset, KnowledgeItem, GeneratedSkill, PublishedPost
)
from auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/overview")
async def get_analytics_overview(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """
    Returns aggregated KPIs for the analytics dashboard.
    All data sourced from the live database — no stubs.
    """
    try:
        # ── Goal counts ───────────────────────────────────
        goals_result = await db.execute(select(Goal))
        goals = goals_result.scalars().all()

        total_goals = len(goals)
        goals_completed = sum(1 for g in goals if g.status == "complete")
        goals_executing = sum(1 for g in goals if g.status == "executing")
        goals_awaiting = sum(1 for g in goals if g.status == "awaiting_approval")
        goals_planning = sum(1 for g in goals if g.status == "planning")
        goals_monitoring = sum(1 for g in goals if g.status == "monitoring")
        goals_failed = sum(1 for g in goals if g.status == "failed")

        # ── Published posts ───────────────────────────────
        posts_result = await db.execute(select(PublishedPost))
        posts = posts_result.scalars().all()

        total_posts = len(posts)
        published_posts = [p for p in posts if p.status == "published"]
        total_published = len(published_posts)

        # Aggregate engagement
        total_impressions = sum(p.impressions for p in published_posts)
        total_likes = sum(p.likes for p in published_posts)
        total_comments = sum(p.comments for p in published_posts)
        total_shares = sum(p.shares for p in published_posts)
        total_reach = sum(p.reach for p in published_posts)

        avg_engagement_rate = (
            sum(p.engagement_rate for p in published_posts) / len(published_posts)
            if published_posts else 0.0
        )

        # ── Platform breakdown ────────────────────────────
        import json
        platform_post_counts: dict[str, int] = {}
        platform_engagement: dict[str, dict] = {}

        for p in published_posts:
            plat = p.platform or "unknown"
            platform_post_counts[plat] = platform_post_counts.get(plat, 0) + 1
            if plat not in platform_engagement:
                platform_engagement[plat] = {"likes": 0, "comments": 0, "shares": 0, "impressions": 0}
            platform_engagement[plat]["likes"] += p.likes
            platform_engagement[plat]["comments"] += p.comments
            platform_engagement[plat]["shares"] += p.shares
            platform_engagement[plat]["impressions"] += p.impressions

        # Also count from goals' platform fields
        goal_platform_counts: dict[str, int] = {}
        for g in goals:
            try:
                platforms = json.loads(g.platforms or "[]")
                for plat in platforms:
                    goal_platform_counts[plat] = goal_platform_counts.get(plat, 0) + 1
            except Exception:
                pass

        # ── Posts per day (last 30 days) ──────────────────
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        posts_by_day: dict[str, int] = {}

        for p in published_posts:
            if p.published_at and p.published_at >= thirty_days_ago:
                day_key = p.published_at.strftime("%Y-%m-%d")
                posts_by_day[day_key] = posts_by_day.get(day_key, 0) + 1

        # Fill in missing days with 0
        posts_per_day = []
        for i in range(30):
            day = (datetime.utcnow() - timedelta(days=29 - i)).strftime("%Y-%m-%d")
            posts_per_day.append({"date": day, "count": posts_by_day.get(day, 0)})

        # ── Agent activity (last 7 days) ──────────────────
        seven_days_ago = datetime.utcnow() - timedelta(days=7)
        logs_result = await db.execute(
            select(AgentLog)
            .where(AgentLog.created_at >= seven_days_ago)
            .order_by(desc(AgentLog.created_at))
        )
        recent_logs = logs_result.scalars().all()

        agent_activity: dict[str, int] = {}
        for log in recent_logs:
            agent_activity[log.agent] = agent_activity.get(log.agent, 0) + 1

        # ── Other counts ──────────────────────────────────
        skills_result = await db.execute(select(func.count()).select_from(GeneratedSkill))
        skill_count = skills_result.scalar() or 0

        docs_result = await db.execute(select(func.count()).select_from(KnowledgeItem))
        doc_count = docs_result.scalar() or 0

        media_result = await db.execute(select(func.count()).select_from(MediaAsset))
        media_count = media_result.scalar() or 0

        # ── Goal status distribution ───────────────────────
        status_distribution = {
            "planning": goals_planning,
            "awaiting_approval": goals_awaiting,
            "executing": goals_executing,
            "monitoring": goals_monitoring,
            "complete": goals_completed,
            "failed": goals_failed,
        }

        return {
            # Top-level KPIs
            "total_goals": total_goals,
            "goals_completed": goals_completed,
            "goals_executing": goals_executing,
            "goals_awaiting_approval": goals_awaiting,
            "goals_planning": goals_planning,
            "goals_monitoring": goals_monitoring,
            "goals_failed": goals_failed,

            # Posts
            "total_posts": total_posts,
            "total_posts_published": total_published,

            # Engagement
            "total_impressions": total_impressions,
            "total_likes": total_likes,
            "total_comments": total_comments,
            "total_shares": total_shares,
            "total_reach": total_reach,
            "avg_engagement_rate": round(avg_engagement_rate, 4),

            # Charts
            "posts_per_day": posts_per_day,
            "platform_breakdown": platform_post_counts,
            "platform_engagement": platform_engagement,
            "goal_platform_counts": goal_platform_counts,
            "status_distribution": status_distribution,
            "agent_activity": agent_activity,

            # Library counts
            "skill_count": skill_count,
            "training_doc_count": doc_count,
            "media_asset_count": media_count,
        }

    except Exception as e:
        logger.error(f"[Analytics] Failed to aggregate: {e}")
        return {
            "total_goals": 0, "goals_completed": 0, "goals_executing": 0,
            "goals_awaiting_approval": 0, "total_posts_published": 0,
            "total_impressions": 0, "avg_engagement_rate": 0.0,
            "posts_per_day": [], "platform_breakdown": {}, "platform_engagement": {},
            "status_distribution": {}, "skill_count": 0, "training_doc_count": 0,
            "media_asset_count": 0, "error": str(e),
        }
