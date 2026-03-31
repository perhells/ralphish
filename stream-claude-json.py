#!/usr/bin/env python3
"""Filter Claude stream-json output to match Claude Code's terminal format."""
import json
import sys

DIM = "\033[2m"
RESET = "\033[0m"
BLUE = "\033[34m"
CYAN = "\033[36m"

last_type = None
tool_depth = 0


def w(text):
    sys.stdout.write(text)
    sys.stdout.flush()


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
                name = block.get("name", "")
                inp = block.get("input", {})
                args = format_tool_args(inp)
                w(f"\n  {CYAN}{name}{RESET}({args})")
                last_type = "tool_use"

    elif t == "user":
        msg = obj.get("message", {})
        for block in msg.get("content", []):
            if isinstance(block, dict) and block.get("type") == "tool_result":
                content = block.get("content", "")
                if isinstance(content, str) and content:
                    lines = content.strip().split("\n")
                    max_lines = 10
                    shown = lines[:max_lines]
                    for i, l in enumerate(shown):
                        prefix = "└" if i == len(shown) - 1 and len(lines) <= max_lines else "│"
                        w(f"\n  {prefix} {DIM}{l}{RESET}")
                    if len(lines) > max_lines:
                        w(f"\n  └ {DIM}… {len(lines) - max_lines} more lines{RESET}")
                last_type = "tool_result"

    elif t == "result":
        text = obj.get("result", "")
        if text:
            if last_type == "thinking":
                w(f"{RESET}\n")
            w(f"\n\n⏺ {text}\n")
            last_type = "result"
