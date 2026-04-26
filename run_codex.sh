#!/bin/bash
cd /home/freebird/projects/ash
nohup codex exec \
  --model gpt-5.5 \
  --full-auto \
  --cd /home/freebird/projects/ash \
  "Read the file CODEX_TASK.md and execute ALL three tasks described in it. Complete every task. Do NOT stop until all tasks are verified working." \
  > /home/freebird/projects/ash/codex_output.txt 2>&1 &
echo "Codex started with PID $!"
