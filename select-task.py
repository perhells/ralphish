#!/usr/bin/env python3
"""Select the next eligible task from progress.yaml (host-side, no PyYAML).

Usage:
    select-task.py <config-dir>            # output next task info
    select-task.py <config-dir> --repos    # list all unique repo paths

Outputs key=value pairs on stdout:
    task_id=<int>       — selected task ID
    repo=<path>         — task's repo field (empty if not set)
    all_done=true       — no todo tasks remain
    no_task=true        — todo tasks exist but none are unblocked
"""
import os
import re
import sys


def parse_value(raw):
    """Clean a YAML scalar value."""
    v = raw.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in ('"', "'"):
        v = v[1:-1]
    return v


def parse_inline_list(raw):
    """Parse [1, 2, 3] or [] into a list of strings."""
    v = raw.strip()
    if not v or v in ('[]', 'null', '~'):
        return []
    v = v.strip('[]')
    return [x.strip().strip('"').strip("'") for x in v.split(',') if x.strip()]


def parse_tasks(path):
    """Extract task dicts from progress.yaml (stdlib only)."""
    with open(path) as f:
        lines = f.readlines()

    tasks = []
    task = None
    in_tasks = False
    in_multiline = False

    for line in lines:
        raw = line.rstrip('\n')
        stripped = raw.lstrip()

        if re.match(r'^tasks:\s*$', raw):
            in_tasks = True
            continue

        if not in_tasks:
            continue

        # End of tasks section: unindented non-empty non-comment line
        if raw and not raw[0].isspace() and not stripped.startswith('#'):
            if task:
                tasks.append(task)
                task = None
            in_tasks = False
            continue

        if not stripped or stripped.startswith('#'):
            continue

        # Inside a multi-line scalar: skip continuation lines
        # (assumes 6-space indent = 2 for list + 4 for field content)
        if in_multiline:
            if raw.startswith('      ') or not stripped:
                continue
            in_multiline = False

        # New list item: '  - key: value'
        m = re.match(r'^  -\s+(\w[\w_]*):\s*(.*)', raw)
        if m:
            if task:
                tasks.append(task)
            task = {}
            key, val = m.group(1), m.group(2).strip()
            if val in ('|', '>', '|+', '|-', '>+', '>-'):
                in_multiline = True
            else:
                task[key] = parse_value(val)
            continue

        # Continuation field: '    key: value'
        m = re.match(r'^    (\w[\w_]*):\s*(.*)', raw)
        if m and task is not None:
            key, val = m.group(1), m.group(2).strip()
            if val in ('|', '>', '|+', '|-', '>+', '>-'):
                in_multiline = True
            else:
                task[key] = parse_value(val)
            continue

    if task:
        tasks.append(task)

    return tasks


def parse_context_assigned_id(path):
    """Read assigned_task_id from .ralphish/context.yaml."""
    try:
        with open(path) as f:
            for line in f:
                m = re.match(r'^assigned_task_id:\s*(\S+)', line)
                if m:
                    v = m.group(1).strip()
                    if v and v not in ('null', '~'):
                        return v
    except FileNotFoundError:
        pass
    return None


def emit_task(task):
    """Print task_id and repo for the given task dict."""
    repo = task.get('repo', '')
    if repo in ('null', '~'):
        repo = ''
    print(f"task_id={task.get('id', '')}")
    print(f"repo={repo}")


def main():
    if len(sys.argv) < 2:
        print("Usage: select-task.py <config-dir> [--repos]", file=sys.stderr)
        sys.exit(1)

    config_dir = sys.argv[1]
    progress_path = os.path.join(config_dir, 'progress.yaml')

    if not os.path.exists(progress_path):
        print(f"Error: {progress_path} not found", file=sys.stderr)
        sys.exit(1)

    tasks = parse_tasks(progress_path)

    # --repos mode: list all unique repo paths for cleanup
    if len(sys.argv) >= 3 and sys.argv[2] == '--repos':
        repos = set()
        for t in tasks:
            repo = t.get('repo', '')
            if repo and repo not in ('null', '~'):
                repos.add(repo)
        for r in sorted(repos):
            print(r)
        sys.exit(0)

    # Classify tasks
    done_ids = set()
    has_todo = False
    for t in tasks:
        s = t.get('status', '')
        if s == 'done':
            done_ids.add(t.get('id', ''))
        elif s == 'todo':
            has_todo = True

    if not has_todo:
        print("all_done=true")
        sys.exit(0)

    # Prefer orchestrator's assignment from context.yaml
    context_path = os.path.join(config_dir, '.ralphish', 'context.yaml')
    assigned_id = parse_context_assigned_id(context_path)
    if assigned_id:
        for t in tasks:
            if t.get('id') == assigned_id and t.get('status') == 'todo':
                emit_task(t)
                sys.exit(0)

    # Fallback: first todo task with all blocked_by satisfied
    # NOTE: blocked_by must use inline list syntax [1, 2] — block lists are not supported
    for t in tasks:
        if t.get('status') != 'todo':
            continue
        blocked = parse_inline_list(t.get('blocked_by', '[]'))
        if all(bid in done_ids for bid in blocked):
            emit_task(t)
            sys.exit(0)

    print("no_task=true")
    sys.exit(0)


if __name__ == '__main__':
    main()
