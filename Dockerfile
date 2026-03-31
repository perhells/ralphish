FROM docker/sandbox-templates:claude-code

USER root

RUN apt-get update && apt-get install -y jq && rm -rf /var/lib/apt/lists/*

COPY setup-claude.sh /home/agent/.claude/setup.sh

USER agent
