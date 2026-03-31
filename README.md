# ralphish

A headless agentic task runner built on [Docker Sandboxes](https://docs.docker.com/ai/sandboxes/) which handles Claude Code authentication. This avoids interactive login when creating new sandboxes.

## Installation

```
./install.sh
```

This builds the Docker image and installs `ralphish` to `~/.local/bin`.

## Setup

Generate an OAuth token and add it to your shell profile:

```
claude setup-token
```

```
export CC_TOKEN=<token>
```

## ralphish

```
ralphish [OPTIONS] [WORKSPACE]
```

Runs Claude headlessly in a sandbox, iterating on tasks defined in a `progress.yaml` file in the workspace. On each iteration Claude will:

1. Find the next eligible task from `progress.yaml`
2. Implement the task on a feature branch
3. Run tests/checks and fix any problems
4. Append progress to `progress.yaml`
5. Stop when all tasks are complete

Output is streamed as JSON and piped through `stream-claude-json.py` for display.

### Options

| Flag               | Description                                          |
| ------------------ | ---------------------------------------------------- |
| --new              | Remove and recreate sandbox before running            |
| --rm               | Remove the sandbox                                   |
| --max-iterations N | Maximum number of iterations to run (default: 1)     |

### Examples

```
ralphish ~/project                    # Run one iteration on ~/project
ralphish --max-iterations 5 .         # Run up to 5 iterations on current directory
ralphish --new --max-iterations 3 .   # Fresh sandbox, up to 3 iterations
ralphish --rm .                       # Remove sandbox for current directory
```

### progress.yaml format

The `progress.yaml` file defines the tasks for `ralphish` to work through. See `example-progress.yaml` for a complete example.

```yaml
next_id: 6
tasks:
  - id: 1
    title: Add rate limiting middleware
    description: |
      Add a token bucket rate limiter as HTTP middleware.
      Configurable per-route limits via environment variables.
      Return 429 with Retry-After header when exceeded.
    status: done
    blocked_by: []
  - id: 4
    title: Add request ID propagation
    description: |
      Generate a UUID request ID in middleware if X-Request-Id header is not present.
      Propagate it via context to all downstream calls and include it in responses.
    status: todo
    blocked_by: [2]
```

Each task has the following fields:

| Field         | Description                                                        |
| ------------- | ------------------------------------------------------------------ |
| `id`          | Unique integer identifier                                          |
| `title`       | Short name for the task                                            |
| `description` | Detailed description of what to implement                          |
| `status`      | `todo` or `done`                                                   |
| `blocked_by`  | List of task IDs that must be completed before this task can start  |

`next_id` tracks the next available ID for new tasks. `ralphish` picks the first `todo` task in the list whose `blocked_by` dependencies are all `done`.

### Creating tasks with Claude Code skills

The [perhells/skills](https://github.com/perhells/skills) collection includes skills that work well as a pipeline for producing `progress.yaml` tasks:

1. **`/grill-me`** — Stress-test your plan or design through an interactive interview, resolving ambiguities before any code is written.
2. **`/write-a-prd`** — Turn the refined plan into a structured PRD through codebase exploration and module design.
3. **`/prd-to-local-implementation-plan`** — Convert the PRD into concrete implementation tasks in `progress.yaml` format, ready for `ralphish` to execute.

Install the skills and run them in sequence to go from idea to runnable task list.
