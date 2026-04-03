# Agent Refresh Prompt

Use this prompt when you want an agent to refresh or rewrite the checkpoint docs after more work has landed.

```text
Refresh the project checkpoint for /Users/davidchen/code/travel-agent.

Goals:
1. Re-read the current implementation and planning docs.
2. Verify the current runtime and test status.
3. Update planning/agent-checkpoint.md so it accurately reflects the current system.
4. Update planning/README.md if the planning doc inventory changed.
5. If needed, update README.md to match actual product behavior.

Minimum reading list:
- README.md
- planning/README.md
- planning/agent-checkpoint.md
- planning/implementation-plan.md
- planning/v1-ui-pass.md
- app/main.py
- app/routes/*.py
- app/services/*.py
- app/storage/*.py
- app/templates/*.html
- tests/test_trip_workflows.py
- tests/test_background_fetch.py
- tests/test_route_preferences.py
- tests/test_booking_resolution.py
- tests/test_web_smoke.py

Verification steps:
- run `git status --short`
- run `uv run pytest -q`

What the refreshed checkpoint must include:
- current product model
- current architecture
- important domain objects
- known-good verified behaviors
- known risks / caveats
- current dirty working tree files
- key files to read first

Constraints:
- do not describe the old planning state as if it were still the live implementation
- distinguish clearly between historical planning docs and current code reality
- keep the checkpoint concise but high-signal
```
