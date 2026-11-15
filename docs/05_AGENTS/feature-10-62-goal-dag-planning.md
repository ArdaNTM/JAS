# Features #10/#62 — deterministic read-only goal DAG planning (partial)

`aura_core.application.goal_planning.plan_goal_steps` validates an
explicit goal graph and computes **possible** prerequisite waves,
immediately ready IDs, blocked IDs and a lower-bound estimated critical
dependency chain. It uses bounded Kahn topological ordering; cycles,
missing references, malformed/duplicate step IDs and inconsistent
claims of already completed dependencies fail closed.

This is a mathematical planning component, not a task executor,
independent attestor, agent dispatcher or scheduler. `claimed_completed`
values come from the caller and are never verified here. The returned
`claimed_completion_verified`, `owner_approval_verified`,
`authorization_checked` and `actions_executed` are all false.
The upstream service must authenticate principal/goal, establish true
task completion with authorized receipts, and submit actual tools through
PermissionEngine/MCP Gateway. No EventBus publishing, background action,
filesystem IO, external provider or privilege is enabled.

Limits: 100 steps, 20 dependencies/step and 500 edges; priorities -10..10;
each duration estimate 1..10,080 minutes. Critical chain duration is an
optimistic user-estimate based on prerequisites, not a schedule, staffing
promise or guarantee of successful work. No due dates, resource
allocation, persistent goals, review UI or automatic progress updates.

#10 long-term goals and #62 task coordination stay TESTING/PARTIAL.
Tests verify actual graph ordering, parallel readiness, deterministic
reordering, cycle detection, invalid identities, budget failure and
untrusted completion claims.

`cd core && uv run pytest -q tests/test_goal_planning.py`,
plus full Core Assurance and Final Release Lock.
