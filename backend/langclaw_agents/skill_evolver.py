"""
Digital Force 2.0 — Self-Evolving Skill Manager
================================================
Gives agents the ability to CREATE and EDIT their own Markdown skill files.

This is the key to true autonomy. Instead of a human editing the skill files,
the agents observe their own performance and rewrite their own instructions.

How it works:
  1. After each campaign, the Reflector calls `update_skill_from_lesson()`.
  2. The lesson is analyzed and mapped to the relevant skill file.
  3. The skill file is surgically updated (a new ## Lesson section is appended
     or an existing instruction is refined).
  4. On the next boot, the agent loads the upgraded skill automatically.

Agents can also CREATE entirely new skill files for new capabilities they
discover — e.g., if SkillForge figures out a new approach to posting on
a new platform, it can write a dedicated skill file for that platform's agent
persona and instructions.

Architecture Rule:
  - Agents NEVER overwrite the core rules sections of a skill file.
  - They can only APPEND to a "## Learned Lessons" section.
  - Humans retain full override authority by editing the file directly.
"""

import logging
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

SKILLS_DIR = Path(__file__).parent.parent / "skills"
SKILLS_DIR.mkdir(parents=True, exist_ok=True)


# ─── Skill File Resolver ───────────────────────────────────────────────────────

AGENT_TO_SKILL_FILE = {
    "content_director": "content_director_skill.md",
    "strategist": "strategist_skill.md",
    "researcher": "researcher_skill.md",
    "orchestrator": "orchestrator_skill.md",
    "publisher": "publisher_skill.md",
    "skillforge": "skillforge_skill.md",
    "monitor": "monitor_skill.md",
    "reflector": "reflector_skill.md",
}


def get_skill_path(agent_name: str) -> Path:
    filename = AGENT_TO_SKILL_FILE.get(agent_name, f"{agent_name}_skill.md")
    return SKILLS_DIR / filename


def read_skill(agent_name: str) -> str:
    """Read the current skill file for an agent. Returns empty string if not found."""
    path = get_skill_path(agent_name)
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


# ─── Append Lesson to Skill File ──────────────────────────────────────────────

async def update_skill_from_lesson(agent_name: str, lesson: str, campaign_context: str = "") -> bool:
    """
    Safely append a new learned lesson to an agent's skill file.
    Never overwrites existing instructions. Only adds to the ## Learned Lessons section.

    Args:
        agent_name: The agent who learned (e.g., "content_director")
        lesson: A single, concrete lesson sentence
        campaign_context: Optional context about what campaign triggered this
    Returns:
        True if file was updated, False if it failed
    """
    path = get_skill_path(agent_name)

    # Create the skill file if it doesn't exist yet
    if not path.exists():
        logger.info(f"[SkillEvolver] Creating new skill file for {agent_name}")
        path.write_text(
            f"# Digital Force — {agent_name.replace('_', ' ').title()} Skill\n\n"
            f"*Auto-created by the self-evolving skill system.*\n\n"
            f"## Learned Lessons\n",
            encoding="utf-8"
        )

    content = path.read_text(encoding="utf-8")
    timestamp = datetime.utcnow().strftime("%Y-%m-%d")

    # Format the lesson entry
    lesson_entry = (
        f"\n- **[{timestamp}]** {lesson}"
        + (f"\n  _(Campaign context: {campaign_context[:120]})_" if campaign_context else "")
    )

    # Append to existing ## Learned Lessons section or create it
    if "## Learned Lessons" in content:
        content = content + lesson_entry
    else:
        content = content + f"\n\n## Learned Lessons\n{lesson_entry}"

    path.write_text(content, encoding="utf-8")
    logger.info(f"[SkillEvolver] Updated {path.name} with new lesson for {agent_name}: {lesson[:80]}...")
    return True


# ─── Create a Brand New Skill File ────────────────────────────────────────────

async def create_skill_file(agent_name: str, role_description: str,
                             core_rules: list[str], output_format: str = "") -> bool:
    """
    Allows SkillForge or the Orchestrator to create a brand new skill file
    for a previously unknown agent or platform-specific persona.

    Args:
        agent_name: Identifier for the new skill (e.g., "tiktok_specialist")
        role_description: What this agent does
        core_rules: List of behavioral rules/principles
        output_format: Optional JSON output format specification
    Returns:
        True if file was created successfully
    """
    path = get_skill_path(agent_name)
    if path.exists():
        logger.warning(f"[SkillEvolver] Skill file for {agent_name} already exists. Use update_skill_from_lesson() instead.")
        return False

    rules_text = "\n".join([f"{i+1}. {rule}" for i, rule in enumerate(core_rules)])
    output_section = f"\n## Output Format\n```\n{output_format}\n```" if output_format else ""

    content = f"""# Digital Force — {agent_name.replace('_', ' ').title()} Skill

*Auto-generated by Digital Force SkillForge on {datetime.utcnow().strftime('%Y-%m-%d')}.*

## Role
{role_description}

## Core Rules
{rules_text}
{output_section}

## Learned Lessons
*(This section grows as the agent learns from its campaigns.)*
"""

    path.write_text(content, encoding="utf-8")
    logger.info(f"[SkillEvolver] Created new skill file: {path.name}")
    return True


# ─── Refine an Existing Rule in a Skill File ──────────────────────────────────

async def refine_skill_rule(agent_name: str, old_rule_fragment: str,
                             refined_rule: str, reason: str = "") -> bool:
    """
    Surgically replace a specific phrase or rule in a skill file.
    Used when the agent detects that a rule is actively causing harm
    (e.g., "LinkedIn posts > 1300 chars" caused low engagement, so it
    changes it to "LinkedIn posts 800-1000 chars").

    Safety: Only replaces the exact fragment. Never deletes sections.
    """
    path = get_skill_path(agent_name)
    if not path.exists():
        logger.warning(f"[SkillEvolver] Cannot refine: skill file for {agent_name} not found.")
        return False

    content = path.read_text(encoding="utf-8")
    if old_rule_fragment not in content:
        logger.warning(f"[SkillEvolver] Fragment '{old_rule_fragment[:40]}' not found in {path.name}. Appending lesson instead.")
        # Fallback: just write a lesson instead
        await update_skill_from_lesson(
            agent_name,
            f"REFINEMENT: Replace '{old_rule_fragment[:60]}' with '{refined_rule[:60]}'. Reason: {reason}",
        )
        return True

    timestamp = datetime.utcnow().strftime("%Y-%m-%d")
    updated = content.replace(
        old_rule_fragment,
        f"{refined_rule} *(refined {timestamp}: {reason[:80]})*"
    )
    path.write_text(updated, encoding="utf-8")
    logger.info(f"[SkillEvolver] Refined rule in {path.name}: '{old_rule_fragment[:40]}' → '{refined_rule[:40]}'")
    return True


# ─── Skill Evolution Summary (for Orchestrator awareness) ─────────────────────

def get_skill_evolution_log(agent_name: str) -> list[str]:
    """
    Read all learned lessons from an agent's skill file.
    Returns a list of lesson strings for the Orchestrator to review.
    """
    content = read_skill(agent_name)
    if "## Learned Lessons" not in content:
        return []

    lessons_section = content.split("## Learned Lessons")[1]
    lines = [line.strip() for line in lessons_section.split("\n") if line.strip().startswith("- **")]
    return lines
