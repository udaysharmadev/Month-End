# Platform guidance

Checked against primary documentation on 28 October 2026. Directory-copy tests
verify the packaged helpers, not discovery or task quality in a running host.

## Claude Code

For repository sessions, install at `.claude/skills/month-end/SKILL.md`.
Skill availability in cloud/account sessions follows different rules; consult
the host documentation rather than assuming a local folder is synchronized.
[Skill locations](https://code.claude.com/docs/en/skills).

Use `/context` to inspect context, `/clear` when switching to unrelated work, and
`/compact` when continuity is needed. Claude Code manages caching and automatic
compaction. Keep diagnostics available rather than suppressing failures to shrink
output. [Context and costs](https://code.claude.com/docs/en/costs).

## Codex and OpenAI

Codex scans repository `.agents/skills` directories between the working directory
and repository root. It initially reads skill metadata and loads full instructions
when selected. Install this folder at `.agents/skills/month-end/`; use the host's
skill picker or `$month-end` where supported. If an update is not visible, restart
the host. [Local skills](https://learn.chatgpt.com/docs/build-skills).

OpenAI API caching depends on reusable prefixes and model-specific eligibility.
Compaction can reduce cache reuse while still reducing total input cost; measure
both. [Prompt caching](https://developers.openai.com/api/docs/guides/prompt-caching).
Responses API compaction is configured by a harness through API requests, not
enabled by this skill. [Compaction](https://developers.openai.com/api/docs/guides/compaction).

## Antigravity and Gemini

The Antigravity App, CLI and standalone IDE document workspace skills at
`.agents/skills/month-end/`, with metadata discovery and on-demand instructions.
Global locations differ between surfaces. This package recommends project scope.
[Agent skills](https://antigravity.google/docs/skills?tab=ide).

Gemini API implicit caching is available on documented supported models. API
cache behavior is not evidence of savings inside Antigravity; collect the host's
actual usage before drawing conclusions.
[Gemini caching](https://ai.google.dev/gemini-api/docs/caching).

## Boundaries

Month End does not change provider settings, permissions, hidden tool catalogs,
model effort, global configuration or subscription quotas. API/harness owners
can evaluate native caching and compaction separately. Keep model, effort,
tools, grading and cache conditions comparable across benchmark arms.
