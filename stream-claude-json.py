#!/usr/bin/env python3
"""Filter Claude stream-json output to match Claude Code's terminal format."""
import json
import shutil
import sys
import textwrap

DIM = "\033[2m"
RESET = "\033[0m"
BLUE = "\033[34m"
CYAN = "\033[36m"

last_type = None
pending_tools = {}  # tool_use_id -> formatted tool header text


def w(text):
    sys.stdout.write(text)
    sys.stdout.flush()


def term_cols():
    return shutil.get_terminal_size((80, 24)).columns


def box_line(corner):
    """Return a horizontal box line like ╭───… filling terminal width."""
    cols = term_cols()
    # 2 spaces indent + 1 corner char = 3 visible chars before the dashes
    fill = cols - 3 - 1  # -1 to avoid filling the last column (which suppresses newline)
    return f"{DIM}{corner}{'─' * max(fill, 1)}{RESET}"


def wrap_in_box(text):
    """Wrap text to fit inside box, returning lines prefixed with │."""
    # Available width: terminal - 2 indent - 1 pipe - 1 space = cols - 4
    width = term_cols() - 4
    wrapped = textwrap.wrap(text, width=max(width, 20), break_on_hyphens=False)
    return wrapped


HIDDEN_KEYS = {"old_string", "new_string"}


def format_tool_args(inp):
    parts = []
    for k, v in inp.items():
        if k in HIDDEN_KEYS:
            continue
        if isinstance(v, str):
            parts.append(f'{k}: "{v}"')
        elif isinstance(v, bool):
            parts.append(f"{k}: {'true' if v else 'false'}")
        elif isinstance(v, (int, float)):
            parts.append(f"{k}: {v}")
    return ", ".join(parts)


for line in sys.stdin:
    try:
        obj = json.loads(line)
    except (json.JSONDecodeError, ValueError):
        continue

    t = obj.get("type", "")

    if t == "assistant":
        msg = obj.get("message", {})
        for block in msg.get("content", []):
            bt = block.get("type", "")

            if bt == "thinking":
                text = block.get("thinking", "")
                if text:
                    if last_type != "thinking":
                        w(f"\n{DIM}")
                    w(text)
                    last_type = "thinking"

            elif bt == "text":
                text = block.get("text", "")
                if text:
                    if last_type == "thinking":
                        w(f"{RESET}\n")
                    if last_type != "text":
                        w(f"\n⏺ ")
                    w(text)
                    last_type = "text"

            elif bt == "tool_use":
                if last_type == "thinking":
                    w(f"{RESET}\n")
                tool_id = block.get("id", "")
                name = block.get("name", "")
                inp = block.get("input", {})
                args = format_tool_args(inp)
                tool_text = f"{name}({args})"
                pending_tools[tool_id] = tool_text
                last_type = "tool_use"

    elif t == "user":
        msg = obj.get("message", {})
        for block in msg.get("content", []):
            if isinstance(block, dict) and block.get("type") == "tool_result":
                tool_id = block.get("tool_use_id", "")
                tool_text = pending_tools.pop(tool_id, None)

                # Print tool header
                w(f"\n  {box_line('╭')}")
                if tool_text:
                    wrapped = wrap_in_box(tool_text)
                    for i, tl in enumerate(wrapped):
                        if i == 0:
                            w(f"\n  {DIM}│{RESET} {CYAN}{tl}{RESET}")
                        else:
                            w(f"\n  {DIM}│   {tl}{RESET}")

                # Print result content
                content = block.get("content", "")
                if isinstance(content, str) and content:
                    lines = content.strip().split("\n")
                    max_lines = 10
                    shown = lines[:max_lines]
                    w(f"\n  {box_line('├')}")
                    for l in shown:
                        w(f"\n  {DIM}│{RESET} {DIM}{l}{RESET}")
                    if len(lines) > max_lines:
                        w(f"\n  {DIM}│ … {len(lines) - max_lines} more lines{RESET}")

                w(f"\n  {box_line('╰')}")
                last_type = "tool_result"

    elif t == "result":
        # Skip — the final response is already printed via the assistant text block
        if last_type == "thinking":
            w(f"{RESET}\n")
        w("\n")
