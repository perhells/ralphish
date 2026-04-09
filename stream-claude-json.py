#!/usr/bin/env python3
"""Format Claude stream-json and Codex JSONL output for terminal display."""
import argparse
import json
import re
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
RED = "\033[31m"

last_type = None
pending_tools = {}  # Claude tool_use_id -> formatted tool header text

codex_streamed_agent_ids = set()
codex_streamed_reasoning_ids = set()
codex_streamed_command_ids = set()


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


def normalize_token(text):
    text = text.replace("-", "_")
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", text)
    return text.lower()


def normalize_event_type(text):
    return ".".join(normalize_token(part) for part in re.split(r"[/.]", text) if part)


def normalize_item_type(text):
    return normalize_token(text)


def event_item_id(obj):
    for key in ("item_id", "itemId"):
        value = obj.get(key)
        if isinstance(value, str) and value:
            return value
    item = obj.get("item")
    if isinstance(item, dict):
        value = item.get("id")
        if isinstance(value, str) and value:
            return value
    return None


def extract_text(*values):
    for value in values:
        if isinstance(value, str) and value:
            return value
    return ""


def print_boxed_block(header, body_lines=None, header_style=CYAN, body_style=DIM, max_lines=10):
    finish_thinking_block()
    w(f"\n  {box_line('╭', '╮')}")
    if header:
        for line in wrap_in_box(header):
            w(f"\n  {box_row(line, header_style)}")

    lines = []
    if body_lines:
        for line in body_lines:
            if isinstance(line, str) and line:
                lines.append(line.expandtabs(4))

    if lines:
        shown = lines[:max_lines]
        w(f"\n  {box_line('├', '┤')}")
        bw = box_width()
        for line in shown:
            if len(line) > bw:
                for wrapped in textwrap.wrap(line, width=bw, break_on_hyphens=False):
                    w(f"\n  {box_row(wrapped, body_style)}")
            else:
                w(f"\n  {box_row(line, body_style)}")
        if len(lines) > max_lines:
            w(f"\n  {box_row(f'… {len(lines) - max_lines} more lines', body_style)}")

    w(f"\n  {box_line('╰', '╯')}")


def start_text_block():
    global last_type
    if last_type == "thinking":
        w(f"{RESET}\n")
    if last_type != "text":
        w("\n⏺ ")
    last_type = "text"


def start_thinking_block():
    global last_type
    if last_type != "thinking":
        if last_type == "text":
            w("\n")
        w(f"\n{DIM}")
    last_type = "thinking"


def finish_thinking_block():
    global last_type
    if last_type == "thinking":
        w(f"{RESET}\n")
        last_type = None


def print_error_block(message):
    global last_type
    finish_thinking_block()
    print_boxed_block(message, header_style=RED)
    last_type = "tool_result"


HIDDEN_KEYS = {"old_string", "new_string", "replace_all", "file_path"}
BASH_HIDDEN_KEYS = {"command", "description", "timeout", "run_in_background"}


def format_tool_args(name, inp):
    parts = []
    # For Bash, show description as prefix and just the command unquoted
    if name == "Bash":
        prefix = inp.get("description", "")
        command = inp.get("command", "")
        inner_parts = [command]
        for k, v in inp.items():
            if k in BASH_HIDDEN_KEYS:
                continue
            if isinstance(v, str):
                inner_parts.append(f'{k}: "{v}"')
            elif isinstance(v, bool):
                inner_parts.append(f"{k}: {'true' if v else 'false'}")
            elif isinstance(v, (int, float)):
                inner_parts.append(f"{k}: {v}")
        return prefix, ", ".join(inner_parts)
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
    return None, ", ".join(parts)


parser = argparse.ArgumentParser()
parser.add_argument("--agent", type=str, default="claude", help="Agent name: claude or codex")
parser.add_argument("--iteration", type=int, default=1)
parser.add_argument("--max", type=int, default=1)
parser.add_argument("--sandbox", type=str, default="")
parser.add_argument("--workspace", type=str, default="")
parser.add_argument("--phase", type=str, default="", help="Phase name: worker, reviewer, orchestrator")
args = parser.parse_args()

PHASE_COLORS = {
    "worker": CYAN,
    "reviewer": YELLOW,
    "orchestrator": GREEN,
}
phase_color = PHASE_COLORS.get(args.phase, MAGENTA)


def box_border(left, right, label=""):
    """Draw a horizontal border, optionally with a centered label."""
    cols = term_cols()
    fill = cols - 5
    if label:
        dashes = fill - len(label)
        ld = dashes // 2
        rd = dashes - ld
        return f"{BOLD}{phase_color}{left}{'─' * ld}{label}{'─' * rd}{right}{RESET}"
    return f"{BOLD}{phase_color}{left}{'─' * fill}{right}{RESET}"


def box_content(left, right="", style=DIM):
    """Draw a content row with optional right-aligned text."""
    cols = term_cols()
    inner = cols - 7  # 2 indent + 2 borders + 2 padding + 1 safety
    if right:
        gap = inner - len(left) - len(right)
        text = left + (" " * max(gap, 1)) + right
    else:
        text = left
    return f"{BOLD}{phase_color}│{RESET} {style}{text.ljust(inner)[:inner]}{RESET} {BOLD}{phase_color}│{RESET}"


def print_start_box():
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if args.phase:
        title = f" Iteration {args.iteration}/{args.max} — {args.phase.title()} "
    else:
        title = f" Iteration {args.iteration}/{args.max} "
    workspace = args.workspace or "unknown"
    agent = args.agent.title()

    rows = [
        box_content(f"Agent: {agent}", f"Sandbox: {args.sandbox}"),
        box_content(f"Workspace: {workspace}", timestamp),
    ]

    w(f"\n  {box_border('╭', '╮', title)}\n")
    for row in rows:
        w(f"  {row}\n")
    w(f"  {box_border('╰', '╯')}\n")


def handle_claude_stream():
    global last_type

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
                        start_text_block()
                        w(text)

                elif bt == "tool_use":
                    if last_type == "thinking":
                        w(f"{RESET}\n")
                    tool_id = block.get("id", "")
                    name = block.get("name", "")
                    inp = block.get("input", {})
                    prefix, tool_args = format_tool_args(name, inp)
                    if prefix:
                        tool_text = f"{prefix} ({tool_args})"
                    else:
                        tool_text = f"{name}({tool_args})"
                    pending_tools[tool_id] = tool_text
                    last_type = "tool_use"

        elif t == "user":
            msg = obj.get("message", {})
            for block in msg.get("content", []):
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    tool_id = block.get("tool_use_id", "")
                    tool_text = pending_tools.pop(tool_id, None)

                    # Print result content
                    content = block.get("content", "")
                    lines = None
                    if isinstance(content, str) and content:
                        lines = content.strip().split("\n")
                    print_boxed_block(tool_text, lines)
                    last_type = "tool_result"

        elif t == "result":
            if last_type == "thinking":
                w(f"{RESET}\n")


def handle_codex_event(obj):
    global last_type

    event_type = normalize_event_type(obj.get("type", ""))
    if not event_type:
        return

    if event_type in {"thread.started", "turn.started", "turn.completed"}:
        return

    if event_type in {"turn.failed", "error"}:
        err = obj.get("error")
        if isinstance(err, dict):
            message = extract_text(err.get("message"), err.get("error"))
            if not message:
                message = json.dumps(err)
        else:
            message = extract_text(obj.get("message"), err)
        print_error_block(message or "Codex run failed")
        return

    item_id = event_item_id(obj)

    if event_type == "item.agent_message.delta":
        delta = extract_text(obj.get("delta"), obj.get("text"), obj.get("content"))
        if delta:
            start_text_block()
            w(delta)
            if item_id:
                codex_streamed_agent_ids.add(item_id)
        return

    if event_type == "item.plan.delta":
        delta = extract_text(obj.get("delta"), obj.get("text"))
        if delta:
            start_text_block()
            w(delta)
        return

    if event_type in {"item.reasoning.summary_text_delta", "item.reasoning.text_delta"}:
        delta = extract_text(obj.get("delta"), obj.get("text"), obj.get("summary"))
        if delta:
            start_thinking_block()
            w(delta)
            if item_id:
                codex_streamed_reasoning_ids.add(item_id)
        return

    if event_type == "item.command_execution.output_delta":
        delta = extract_text(obj.get("delta"), obj.get("output"), obj.get("text"))
        if delta:
            finish_thinking_block()
            w(delta)
            last_type = "tool_result"
            if item_id:
                codex_streamed_command_ids.add(item_id)
        return

    if event_type not in {"item.started", "item.completed"}:
        return

    item = obj.get("item", {})
    if not isinstance(item, dict):
        return

    item_id = extract_text(item.get("id"), item_id)
    item_type = normalize_item_type(item.get("type", ""))

    if item_type == "agent_message" and event_type == "item.completed":
        if item_id and item_id in codex_streamed_agent_ids:
            return
        text = extract_text(item.get("text"))
        if text:
            start_text_block()
            w(text)
        return

    if item_type == "reasoning" and event_type == "item.completed":
        if item_id and item_id in codex_streamed_reasoning_ids:
            return
        summary = item.get("summary")
        if isinstance(summary, list):
            summary = " ".join(part for part in summary if isinstance(part, str))
        text = extract_text(summary, item.get("text"))
        if text:
            start_thinking_block()
            w(text)
        return

    if item_type == "command_execution":
        command = extract_text(item.get("command")) or "Command execution"
        status = extract_text(item.get("status"))
        header = f"{command} [{status}]" if status else command

        if event_type == "item.started":
            print_boxed_block(header)
            last_type = "tool_result"
            return

        lines = []
        aggregated_output = extract_text(item.get("aggregated_output"), item.get("aggregatedOutput"))
        if aggregated_output and not (item_id and item_id in codex_streamed_command_ids):
            lines.extend(aggregated_output.splitlines())
        exit_code = item.get("exit_code", item.get("exitCode"))
        if exit_code not in (None, ""):
            lines.append(f"exit_code: {exit_code}")
        print_boxed_block(header, lines or None)
        last_type = "tool_result"
        return

    if item_type == "mcp_tool_call" and event_type == "item.completed":
        tool = extract_text(item.get("tool")) or "MCP tool"
        status = extract_text(item.get("status"))
        header = f"{tool} [{status}]" if status else tool
        result = item.get("result")
        error = item.get("error")
        lines = []
        if isinstance(result, str) and result:
            lines.extend(result.splitlines())
        elif result:
            lines.append(json.dumps(result))
        if isinstance(error, str) and error:
            lines.append(error)
        elif error:
            lines.append(json.dumps(error))
        print_boxed_block(header, lines or None)
        last_type = "tool_result"
        return

    if item_type == "web_search" and event_type == "item.started":
        query = extract_text(item.get("query")) or "web search"
        print_boxed_block(f"WebSearch({query})")
        last_type = "tool_result"
        return

    if item_type == "file_change" and event_type == "item.completed":
        status = extract_text(item.get("status"))
        header = f"File changes [{status}]" if status else "File changes"
        lines = []
        for change in item.get("changes", [])[:10]:
            if not isinstance(change, dict):
                continue
            path = extract_text(change.get("path"))
            kind = extract_text(change.get("kind"))
            if path and kind:
                lines.append(f"{kind}: {path}")
            elif path or kind:
                lines.append(path or kind)
        print_boxed_block(header, lines or None)
        last_type = "tool_result"


def handle_codex_stream():
    for line in sys.stdin:
        try:
            obj = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            raw = line.rstrip("\n")
            if raw:
                finish_thinking_block()
                w(f"\n{raw}\n")
            continue

        handle_codex_event(obj)


print_start_box()

if args.agent == "codex":
    handle_codex_stream()
else:
    handle_claude_stream()

if last_type == "thinking":
    w(f"{RESET}\n")
w("\n")
