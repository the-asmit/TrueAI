"""
Fix Engineer Agent — writes the code change.

Produces search/replace edits (never a raw diff): each edit quotes the exact
current code and its replacement.  ``app.services.patching`` applies them
deterministically and builds the real diff.  If an edit does not apply, or
the Reviewer asks for changes, the Fix Engineer is called again with that
feedback (up to ``MAX_FIX_ATTEMPTS``).
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from app.agents.base import BaseAgent, optional_text, required_choice, required_text, tag, tags
from app.agents.formatting import format_code, format_frames, format_incident
from app.core.errors import AgentOutputError
from app.core.security import fence_untrusted, restore_neutralized


class ProposedEdit(BaseModel):
    path: str
    find_exact: str
    replace_with: str


class FixOutput(BaseModel):
    summary: str = Field(default="", max_length=120)
    rationale: str = Field(default="", max_length=2000)
    risk: Literal["low", "medium", "high"] = "medium"
    edits: List[ProposedEdit] = Field(default_factory=list)
    cannot_fix: Optional[str] = None


class FixEngineerAgent(BaseAgent[FixOutput]):
    name = "fix_engineer"
    title = "Fix Engineer Agent"
    system_prompt = """
You are the Fix Engineer Agent in TrueAI. You write the smallest correct code change that fixes a confirmed
root cause. A human will review your change as a pull request, so it must be clean and obviously safe.

Rules:
- Change only what is needed to fix the root cause. No refactors, renames, reformatting or unrelated fixes.
- Match the file's existing style, naming and indentation exactly.
- Handle the failing case explicitly (validate, guard, default, or raise a clear error) — never silently
  swallow exceptions or hide the problem.
- Do not add dependencies, network calls, shell commands, eval/exec, or credentials. Do not weaken
  authentication, authorisation, validation or TLS.
- Only edit the files shown to you.
- If no safe code change can fix this, reply with <cannot_fix> and explain why instead of guessing.

Edit format: each <edit> quotes EXACT current lines in <find_exact> (copied character-for-character from the
file, WITHOUT the line-number gutter, including indentation) and gives their replacement in <replace_with>.
<find_exact> must match exactly one place in the file — include enough surrounding lines to be unique
(typically 3–8 lines). Use several <edit> blocks for separate locations.
""".strip()

    def build_prompt(
        self,
        *,
        event: Dict[str, Any],
        investigation: Dict[str, Any],
        code_context: Dict[str, Dict[str, Any]],
        attempt: int,
        max_attempts: int,
        feedback: List[str],
        previous_diff: Optional[str],
        **_: Any,
    ) -> str:
        sections = [
            f"Fix attempt {attempt} of {max_attempts}.",
            "INCIDENT\n" + format_incident(event),
            "STACK FRAMES (crash site last)\n" + format_frames(event.get("frames") or [], limit=6),
            "ROOT CAUSE (from the Investigator Agent)\n"
            f"Root cause: {investigation.get('root_cause')}\n"
            f"Explanation: {investigation.get('explanation')}\n"
            f"Suggested strategy: {investigation.get('fix_strategy') or '(none given)'}\n"
            f"Culprit: {investigation.get('culprit_file') or 'unknown'}:{investigation.get('culprit_line') or '?'}",
            "FILES YOU MAY EDIT (the line-number gutter is NOT part of the file)\n" + format_code(code_context),
        ]
        if previous_diff:
            sections.append("YOUR PREVIOUS ATTEMPT (as a diff)\n" + fence_untrusted("previous_diff", previous_diff, max_len=6000))
        if feedback:
            sections.append(
                "FEEDBACK YOU MUST ADDRESS IN THIS ATTEMPT\n" + "\n".join(f"- {item}" for item in feedback[-6:])
            )
        sections.append(
            "Reply with exactly these tags and nothing else:\n"
            "<summary>Imperative commit title, max 72 characters (e.g. 'Handle missing user_id in dashboard view')</summary>\n"
            "<rationale>Why this change fixes the root cause and why it is safe.</rationale>\n"
            "<risk>low | medium | high</risk>\n"
            "<edit>\n<file_path>path/from/the/file/list.ext</file_path>\n<find_exact>\nexact existing lines\n</find_exact>\n"
            "<replace_with>\nreplacement lines\n</replace_with>\n</edit>\n"
            "(repeat <edit> as needed)\n\n"
            "OR, if no safe code change exists:\n<cannot_fix>reason</cannot_fix>"
        )
        return "\n\n".join(sections)

    def parse(self, text: str) -> FixOutput:
        cannot_fix = optional_text(text, "cannot_fix", max_len=1500)
        edits: List[ProposedEdit] = []
        for block in tags(text, "edit"):
            path = (tag(block, "file_path") or "").strip().strip("`'\" ")
            find_exact = tag(block, "find_exact")
            replace_with = tag(block, "replace_with")
            if not path or find_exact is None or replace_with is None:
                raise AgentOutputError("every <edit> needs <file_path>, <find_exact> and <replace_with>")
            edits.append(
                ProposedEdit(
                    path=path.lstrip("/"),
                    find_exact=restore_neutralized(find_exact),
                    replace_with=restore_neutralized(replace_with),
                )
            )
        if not edits and not cannot_fix:
            raise AgentOutputError("reply must contain at least one <edit> block or a <cannot_fix> reason")
        if edits:
            return FixOutput(
                summary=required_text(text, "summary", max_len=120),
                rationale=optional_text(text, "rationale", max_len=2000) or "",
                risk=required_choice(text, "risk", ("low", "medium", "high")),  # type: ignore[arg-type]
                edits=edits[:10],
            )
        return FixOutput(cannot_fix=cannot_fix)
