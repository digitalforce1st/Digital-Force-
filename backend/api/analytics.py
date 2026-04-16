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
        total_goals = await db.scalar(select(func.count(Goal.id))) or 0
        
        goal_status_counts = await db.execute(
            select(Goal.status, func.count()).group_by(Goal.status)
        )
        status_distribution = {
            "planning": 0, "awaiting_approval": 0, "executing": 0,
            "monitoring": 0, "complete": 0, "failed": 0
        }
        for status, count in goal_status_counts:
            status_distribution[status] = count
            
        goals_completed = status_distribution["complete"]
        goals_executing = status_distribution["executing"]
        goals_awaiting = status_distribution["awaiting_approval"]
        goals_planning = status_distribution["planning"]
        goals_monitoring = status_distribution["monitoring"]
        goals_failed = status_distribution["failed"]

        # ── Published posts stats ───────────────────────────────
        total_posts = await db.scalar(select(func.count(PublishedPost.id))) or 0
        
        post_stats = await db.execute(
            select(
                func.count(PublishedPost.id),
                func.sum(PublishedPost.impressions),
                func.sum(PublishedPost.likes),
                func.sum(PublishedPost.comments),
                func.sum(PublishedPost.shares),
                func.sum(PublishedPost.reach),
                func.avg(PublishedPost.engagement_rate)
            ).where(PublishedPost.status == "published")
        )
        pub_count, tot_imp, tot_likes, tot_com, tot_shares, tot_reach, avg_eng = post_stats.first() or (0,0,0,0,0,0,0.0)
        
        total_published = pub_count or 0
        total_impressions = tot_imp or 0
        total_likes = tot_likes or 0
        total_comments = tot_com or 0
        total_shares = tot_shares or 0
        total_reach = tot_reach or 0
        avg_engagement_rate = float(avg_eng or 0.0)

        # ── Platform breakdown (Posts) ────────────────────────────
        platform_post_counts: dict[str, int] = {}
        platform_engagement: dict[str, dict] = {}
        
        platform_stats = await db.execute(
            select(
                PublishedPost.platform,
                func.count(PublishedPost.id),
                func.sum(PublishedPost.likes),
                func.sum(PublishedPost.comments),
                func.sum(PublishedPost.shares),
                func.sum(PublishedPost.impressions)
            ).where(PublishedPost.status == "published").group_by(PublishedPost.platform)
        )
        for p_plat, p_count, p_likes, p_com, p_shares, p_imp in platform_stats:
            plat = p_plat or "unknown"
            platform_post_counts[plat] = p_count or 0
            platform_engagement[plat] = {
                "likes": p_likes or 0, "comments": p_com or 0, 
                "shares": p_shares or 0, "impressions": p_imp or 0
            }

        # Also count from goals' platform fields (memory optimized by only selecting platforms)
        import json
        goal_platform_counts: dict[str, int] = {}
        goal_platforms_raw = await db.execute(select(Goal.platforms).where(Goal.platforms.is_not(None)))
        for g_plat in goal_platforms_raw.scalars():
            try:
                for plat in json.loads(g_plat or "[]"):
                    goal_platform_counts[plat] = goal_platform_counts.get(plat, 0) + 1
            except Exception:
                pass

        # ── Posts per day (last 30 days) ──────────────────
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        posts_by_day: dict[str, int] = {}
        
        recent_posts_dates = await db.execute(
            select(PublishedPost.published_at)
            .where(PublishedPost.status == "published")
            .where(PublishedPost.published_at >= thirty_days_ago)
        )
        for pub_at in recent_posts_dates.scalars():
            if pub_at:
                day_key = pub_at.strftime("%Y-%m-%d")
                posts_by_day[day_key] = posts_by_day.get(day_key, 0) + 1

        # Fill in missing days with 0
        posts_per_day = []
        for i in range(30):
            day = (datetime.utcnow() - timedelta(days=29 - i)).strftime("%Y-%m-%d")
            posts_per_day.append({"date": day, "count": posts_by_day.get(day, 0)})

        # ── Agent activity (last 7 days) ──────────────────
        seven_days_ago = datetime.utcnow() - timedelta(days=7)
        agent_counts_query = await db.execute(
            select(AgentLog.agent, func.count(AgentLog.id))
            .where(AgentLog.created_at >= seven_days_ago)
            .group_by(AgentLog.agent)
        )
        agent_activity = {agent: count for agent, count in agent_counts_query if agent}

        # ── Other counts ──────────────────────────────────
        skill_count = await db.scalar(select(func.count(GeneratedSkill.id))) or 0
        doc_count = await db.scalar(select(func.count(KnowledgeItem.id))) or 0
        media_count = await db.scalar(select(func.count(MediaAsset.id))) or 0

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
        logger.error("Failed to aggregate: %s", str(e), exc_info=True)
        return {
            "total_goals": 0, "goals_completed": 0, "goals_executing": 0,
            "goals_awaiting_approval": 0, "total_posts_published": 0,
            "total_impressions": 0, "avg_engagement_rate": 0.0,
            "posts_per_day": [], "platform_breakdown": {}, "platform_engagement": {},
            "status_distribution": {}, "skill_count": 0, "training_doc_count": 0,
            "media_asset_count": 0, "error": str(e),
        }
