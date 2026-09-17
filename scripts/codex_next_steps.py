"""Local NEXT_STEPS to CODEX_CHAT mission selection helper."""

from __future__ import annotations

import argparse
import datetime as _dt
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


DEFAULT_NEXT_STEPS = Path("docs/00-start-here/NEXT_STEPS.md")
DEFAULT_CODEX_CHAT = Path("planning/CODEX_CHAT.md")


@dataclass(frozen=True)
class MissionOption:
    index: int
    priority: str
    title: str
    source_line: str


def _clean_line(line: str) -> str:
    return re.sub(r"\s+", " ", line.strip().lstrip("-*0123456789.[] ")).strip()


def extract_options(next_steps_text: str, limit: int = 5) -> list[MissionOption]:
    if not next_steps_text or not next_steps_text.strip():
        raise ValueError("NEXT_STEPS content is empty")

    candidates: list[tuple[str, str]] = []
    current_priority = ""
    for raw_line in next_steps_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        header_match = re.search(r"\b(P0|P1|P2)\b", line, flags=re.IGNORECASE)
        if header_match:
            current_priority = header_match.group(1).upper()

        if not current_priority:
            continue

        is_heading = line.startswith("#")
        is_bullet = line.startswith(("-", "*")) or re.match(r"^\d+[.)]\s+", line)
        has_task_marker = re.search(r"\b(TODO|NEXT|MISSION|BUILD|FIX|IMPLEMENT|REVIEW|P0|P1|P2)\b", line, re.IGNORECASE)
        priority_heading_only = bool(is_heading and header_match)
        if is_heading or is_bullet or has_task_marker:
            if priority_heading_only:
                continue
            title = _clean_line(line.replace("#", " "))
            title = re.sub(r"^\bP[0-2]\b[:\s-]*", "", title, flags=re.IGNORECASE).strip()
            if title and len(title) >= 8:
                candidates.append((current_priority, title))

    seen: set[str] = set()
    options: list[MissionOption] = []
    for priority, title in candidates:
        key = title.lower()
        if key in seen:
            continue
        seen.add(key)
        options.append(MissionOption(len(options) + 1, priority, title, f"{priority}: {title}"))
        if len(options) >= limit:
            break

    if not options:
        raise ValueError("No P0/P1/P2 mission options found in NEXT_STEPS")
    return options


def read_options(path: Path = DEFAULT_NEXT_STEPS, limit: int = 5) -> list[MissionOption]:
    if not path.exists():
        raise FileNotFoundError(f"NEXT_STEPS file not found: {path}")
    return extract_options(path.read_text(encoding="utf-8"), limit=limit)


def render_code_chat(option: MissionOption, owner_intent: str = "") -> str:
    now = _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()
    intent = owner_intent.strip() or option.title
    return f"""# CODEX_CHAT

Updated: {now}

## ACTIVE MISSION
{option.title}

## OWNER INTENT
{intent}

## AUTHORITY LEVEL
GREEN for scoped inspect/build/test/docs/commit/PR work. RED-zone actions require owner approval.

## ALLOWED FILES
Set by the mission prompt. Default: code, docs, scripts, and tests directly required for the active mission.

## FORBIDDEN FILES
.env, .claude/, screenshots/, external_sources/, static/assets/, test-results/, planning/Prompts.md, secrets, generated exports, unapproved migrations.

## DONE WHEN
- The requested behavior is implemented.
- Relevant deterministic tests pass.
- scripts/verify_mission.ps1 passes.
- No hard stop or red-zone action occurred.

## TESTS TO RUN
- Focused unit tests for changed files.
- scripts/verify_mission.ps1.

## PRESSURE TESTS
- Check failure and fallback paths touched by the mission.
- Confirm no customer/payment/reservation/stock-lifecycle/public-post side effects.

## CURRENT STATUS
selected_from_next_steps: {option.priority}
status: queued

## FINAL REPORT
Pending.
"""


def archive_existing(path: Path) -> Path | None:
    if not path.exists() or not path.read_text(encoding="utf-8", errors="ignore").strip():
        return None
    archive_dir = path.parent / ".archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    stamp = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive_path = archive_dir / f"{stamp}.{path.name}"
    shutil.copy2(path, archive_path)
    return archive_path


def write_selected_mission(
    option_number: int,
    *,
    next_steps_path: Path = DEFAULT_NEXT_STEPS,
    codex_chat_path: Path = DEFAULT_CODEX_CHAT,
    owner_intent: str = "",
    archive: bool = True,
) -> tuple[MissionOption, Path | None]:
    options = read_options(next_steps_path)
    if option_number < 1 or option_number > len(options):
        raise ValueError(f"Invalid option {option_number}; expected 1-{len(options)}")
    option = options[option_number - 1]
    codex_chat_path.parent.mkdir(parents=True, exist_ok=True)
    archive_path = archive_existing(codex_chat_path) if archive else None
    codex_chat_path.write_text(render_code_chat(option, owner_intent=owner_intent), encoding="utf-8")
    return option, archive_path


def format_options(options: Iterable[MissionOption]) -> str:
    return "\n".join(f"{option.index}. [{option.priority}] {option.title}" for option in options)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extract mission options from NEXT_STEPS and optionally update CODEX_CHAT.")
    parser.add_argument("--next-steps", type=Path, default=DEFAULT_NEXT_STEPS)
    parser.add_argument("--codex-chat", type=Path, default=DEFAULT_CODEX_CHAT)
    parser.add_argument("--select", type=int, default=0, help="Option number to write to CODEX_CHAT.")
    parser.add_argument("--owner-intent", default="")
    parser.add_argument("--no-archive", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.select:
        option, archive_path = write_selected_mission(
            args.select,
            next_steps_path=args.next_steps,
            codex_chat_path=args.codex_chat,
            owner_intent=args.owner_intent,
            archive=not args.no_archive,
        )
        print(f"Selected [{option.priority}] {option.title}")
        if archive_path:
            print(f"Archived previous CODEX_CHAT to {archive_path}")
    else:
        print(format_options(read_options(args.next_steps)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
