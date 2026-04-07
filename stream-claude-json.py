#!/usr/bin/env python3
"""Filter Claude stream-json output to match Claude Code's terminal format."""
import argparse
import json
import shutil
import sys
import textwrap
from datetime import datetime

DIM = "\033[2m"
RESET = "\033[0m"
BOLD = "\033[1m"
BLUE = "\033[34m"
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
MAGENTA = "\033[35m"

last_type = None
pending_tools = {}  # tool_use_id -> formatted tool header text


def w(text):
    sys.stdout.write(text)
    sys.stdout.flush()


def term_cols():
    return shutil.get_terminal_size((80, 24)).columns


def box_width():
    """Inner content width: cols - 2 indent - 2 border - 2 padding - 1 safety."""
    return max(term_cols() - 7, 20)


def box_line(left, right):
    """Return a horizontal box line like ╭───…───╮ filling terminal width."""
    cols = term_cols()
    # 2 indent + left corner + dashes + right corner = cols - 1
    fill = cols - 5  # 2 indent + 2 corners + 1 safety
    return f"{DIM}{left}{'─' * max(fill, 1)}{right}{RESET}"


def box_row(text, style=""):
    """Return a row like │ text   │ padded to fill the box."""
    bw = box_width()
    padded = text.ljust(bw)[:bw]
    return f"{DIM}│{RESET} {style}{padded}{RESET} {DIM}│{RESET}"


def wrap_in_box(text):
    """Wrap text to fit inside box, returning wrapped lines."""
    return textwrap.wrap(text, width=max(box_width(), 20), break_on_hyphens=False)


HIDDEN_KEYS = {"old_string", "new_string", "replace_all", "file_path"}


def format_tool_args(name, inp):
    parts = []
    # For tools with file_path, show just the filename unquoted as the first arg
    if "file_path" in inp:
        filename = inp["file_path"].rsplit("/", 1)[-1]
        parts.append(filename)
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


parser = argparse.ArgumentParser()
parser.add_argument("--iteration", type=int, default=1)
parser.add_argument("--max", type=int, default=1)
parser.add_argument("--sandbox", type=str, default="")
parser.add_argument("--workspace", type=str, default="")
args = parser.parse_args()


def box_border(left, right, label=""):
    """Draw a horizontal border, optionally with a centered label."""
    cols = term_cols()
    fill = cols - 5
    if label:
        dashes = fill - len(label)
        ld = dashes // 2
        rd = dashes - ld
        return f"{BOLD}{MAGENTA}{left}{'─' * ld}{label}{'─' * rd}{right}{RESET}"
    return f"{BOLD}{MAGENTA}{left}{'─' * fill}{right}{RESET}"


def box_content(left, right="", style=DIM):
    """Draw a content row with optional right-aligned text."""
    cols = term_cols()
    inner = cols - 7  # 2 indent + 2 borders + 2 padding + 1 safety
    if right:
        gap = inner - len(left) - len(right)
        text = left + (" " * max(gap, 1)) + right
    else:
        text = left
    return f"{BOLD}{MAGENTA}│{RESET} {style}{text.ljust(inner)[:inner]}{RESET} {BOLD}{MAGENTA}│{RESET}"


def print_start_box():
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    title = f" Iteration {args.iteration}/{args.max} "
    workspace = args.workspace or "unknown"

    rows = [
        box_content(f"Sandbox: {args.sandbox}"),
        box_content(f"Workspace: {workspace}", timestamp),
    ]

    w(f"\n  {box_border('╭', '╮', title)}\n")
    for row in rows:
        w(f"  {row}\n")
    w(f"  {box_border('╰', '╯')}\n")


print_start_box()

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
                args = format_tool_args(name, inp)
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
                w(f"\n  {box_line('╭', '╮')}")
                if tool_text:
                    for tl in wrap_in_box(tool_text):
                        w(f"\n  {box_row(tl, CYAN)}")

                # Print result content
                content = block.get("content", "")
                if isinstance(content, str) and content:
                    lines = content.strip().split("\n")
                    lines = [l.expandtabs(4) for l in lines]
                    max_lines = 10
                    shown = lines[:max_lines]
                    w(f"\n  {box_line('├', '┤')}")
                    bw = box_width()
                    for l in shown:
                        if len(l) > bw:
                            for wl in textwrap.wrap(l, width=bw, break_on_hyphens=False):
                                w(f"\n  {box_row(wl, DIM)}")
                        else:
                            w(f"\n  {box_row(l, DIM)}")
                    if len(lines) > max_lines:
                        w(f"\n  {box_row(f'… {len(lines) - max_lines} more lines', DIM)}")

                w(f"\n  {box_line('╰', '╯')}")
                last_type = "tool_result"

    elif t == "result":
        # Skip — the final response is already printed via the assistant text block
        if last_type == "thinking":
            w(f"{RESET}\n")
        w("\n")
