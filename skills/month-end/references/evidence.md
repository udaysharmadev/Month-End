# Evidence register

Snapshot `2026-10-28.1`, reviewed on 28 October 2026. Source identity and the bounded claims below were checked for every S01–S31 entry in the supplied PRD. Papers were reviewed at the title/venue or pinned revision and abstract level; their experiments were not independently reproduced. Repository and community material is described as such. No source proves that Month End lowers live model spending.

The original S01 article was unavailable to retrieval. Current official Claude Code context/cost documentation is the replacement; the unavailable page is not a required operational dependency. See [platform guidance](platforms.md) for current installation/context recommendations.

## Official documentation and format

| ID | Source | What was checked and what it supports |
| --- | --- | --- |
| S01 | [Maximizing the value of your Claude Code sessions](https://claude.com/resources/articles/maximizing-the-value-of-your-claude-code-sessions) | unavailable: Original article unavailable to retrieval; use current official context/cost guidance instead. |
| S02 | [Effective context engineering for AI agents](https://www.anthropic.com/research/effective-context-engineering-for-ai-agents) | verified: Context selection and lifecycle mechanisms; no Month End outcome proof. |
| S03 | [Prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching) | verified: Provider cache behavior; not a control exposed by a Markdown skill. |
| S04 | [Manage tool context](https://platform.claude.com/docs/en/agents-and-tools/tool-use/manage-tool-context) | verified: Tool-context guidance; API/harness controls are separate from skill instructions. |
| S05 | [Context engineering: memory, compaction, and tool clearing](https://platform.claude.com/cookbook/tool-use-context-engineering-context-engineering-tools) | verified: Lifecycle alternatives and their tradeoffs; not a Month End reproduction. |
| S06 | [Prompt caching](https://developers.openai.com/api/docs/guides/prompt-caching) | verified: Stable reusable context and compaction can affect cache reuse; model-specific rules apply. |
| S07 | [Compaction](https://developers.openai.com/api/docs/guides/compaction) | verified: Native Responses compaction is configured by API/harness owners. |
| S08 | [Testing Agent Skills Systematically with Evals](https://developers.openai.com/blog/eval-skills) | verified: Define success, capture behavior, and grade observable outcomes. |
| S09 | [Context caching](https://ai.google.dev/gemini-api/docs/caching) | verified: Gemini implicit caching behavior; no inference about Antigravity billing. |
| S10 | [Agent Skills specification](https://agentskills.io/specification) | verified: Manifest and package format, including optional compatibility metadata. |
| S29 | [Rethinking skills and prompts for GPT-6 Astra](https://developers.openai.com/blog/rethinking-skills-and-prompts-for-gpt-6-astra) | verified: Scoped descriptions and progressive disclosure; model-specific advice is not universal. |
| S30 | [Antigravity agent skills](https://antigravity.google/docs/skills?tab=ide) | verified: Project skill path and progressive disclosure; global paths differ by surface. |
| S31 | [Skills in OpenAI API](https://developers.openai.com/api/docs/guides/tools-skills) | verified: Skill package/API integration boundaries; no changes made to host API settings. |
| A01 | [Manage costs effectively](https://code.claude.com/docs/en/costs) | verified: Current official replacement for unavailable S01: context inspection, task boundaries and compaction. |

## Peer-reviewed research

| ID | Source | What was checked and what it supports |
| --- | --- | --- |
| S11 | [LLMLingua: Compressing Prompts for Accelerated Inference of Large Language Models](https://aclanthology.org/2023.emnlp-main.825/) | abstract reviewed: Task-specific prompt compression; does not establish safe exact-code compression. |
| S12 | [LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression](https://aclanthology.org/2024.acl-long.91/) | abstract reviewed: Long-context task performance and compression under its evaluated conditions. |
| S13 | [LLMLingua-2: Data Distillation for Efficient and Faithful Task-Agnostic Prompt Compression](https://aclanthology.org/2024.findings-acl.57/) | abstract reviewed: Extractive prompt compression; transfer to exact source editing is unproven. |
| S14 | [Lost in the Middle: How Language Models Use Long Contexts](https://aclanthology.org/2024.tacl-1.9/) | abstract reviewed: Placement-sensitive retrieval in the tested tasks and models. |

## Preprints

| ID | Source | What was checked and what it supports |
| --- | --- | --- |
| S15 | [Token Reduction Is Not Cost Reduction](https://arxiv.org/abs/2607.12161v5) | abstract reviewed: Reports a counterexample to equating delivered token reduction with billed savings. |
| S16 | [SkillReducer: Optimizing LLM Agent Skills for Token Efficiency](https://arxiv.org/abs/2603.29919v2) | abstract reviewed: Instruction/routing overhead and progressive-disclosure optimization in its sample. |
| S17 | [SWE-Skills-Bench: Do Agent Skills Actually Help in Real-World Software Engineering?](https://arxiv.org/abs/2603.15401v2) | abstract reviewed: Most sampled skills did not significantly improve outcomes; avoid broad universal claims. |
| S18 | [TokenEconomizer: Experience-Driven Black-Box Cost Control for Coding Agents](https://arxiv.org/abs/2610.22732v1) | abstract reviewed: Adaptive external-controller results under its own tested conditions. |
| S19 | [An Empirical Cost Attribution of Context-Compression Gateways in Multi-Turn Coding Agents](https://arxiv.org/abs/2609.22114v1) | abstract reviewed: Separates tool-schema filtering, content compression and history summarization. |

## Implementations and community material

| ID | Source | What was checked and what it supports |
| --- | --- | --- |
| S20 | [RTK](https://github.com/rtk-ai/rtk) | identity reviewed: Repository identity and stated command-output proxy purpose; claims not independently reproduced. |
| S21 | [Token Saver](https://www.skills.sh/otnc/skills_ai-agent-saving-tech/token-saver) | identity reviewed: Agent-neutral lean-work skill and setup audit; not causal performance evidence. |
| S22 | [Agent Skills for Context Engineering](https://github.com/muratcankoylan/Agent-Skills-for-Context-Engineering) | identity reviewed: Collection and modular-reference structure; no independent outcome validation. |
| S23 | [Anthropic Skills](https://github.com/anthropics/skills) | identity reviewed: Public skill-package examples; repository identity verified. |
| S24 | [Vercel Skills CLI](https://github.com/vercel-labs/skills) | identity reviewed: Installer/distribution tooling; Month End remote install remains pending publication. |
| S25 | [Superpowers](https://github.com/obra/superpowers) | identity reviewed: Skill/workflow framework; ergonomics reference, not proof of savings. |
| S26 | [Everything Claude Code / ECC](https://github.com/affaan-m/ECC) | identity reviewed: Multi-host harness/skill project; no claims independently reproduced here. |
| S27 | [I saved 10M tokens (89%) on my Claude Code sessions with a CLI proxy](https://www.reddit.com/r/ClaudeAI/comments/1r2tt7q/i_saved_10m_tokens_89_on_my_claude_code_sessions/) | anecdote reviewed: Author self-report; local output/usage figures do not establish billed cost per successful task. |
| S28 | [I benchmarked 5 token saving tools across Codex and Claude code](https://www.reddit.com/r/ClaudeAI/comments/1viyokr/i_benchmarked_5_token_saving_tools_across_codex/) | anecdote reviewed: Community comparison with disclosed competitive involvement; not an independent Month End evaluation. |
| C01 | [I cut Codex token usage about 50% with one AGENTS.md rule](https://www.reddit.com/r/codex/comments/1t6iulo/i_cut_codex_token_usage_50_with_one_agentsmd_rule/) | anecdote reviewed: Single huge-line hazard is a useful fixture idea. The post also suggests skipping checks; Month End does not adopt that rule or validate its percentage. |

## Evidence rules

- Provider documentation establishes supported mechanisms and interfaces, not this product's success-adjusted economics.
- Compression and long-context papers studied specific tasks and models. Their results do not authorize semantic rewriting of exact code, stack traces or patch anchors.
- Performance claims from projects and social posts remain attributed claims. Popularity, installs and headline percentages do not establish causality.
- C01 motivates a bounded-line regression case only. Month End does not adopt its suggestion to omit necessary checks or modify proprietary prompts.
- No leaked prompt mirror, Quora page, or inaccessible X post is a required source. Such material cannot establish provider behavior.
- Update changing primary documentation before each release or within 90 days. The source checkout includes a dated machine-readable registry and a local freshness check; no background network monitor is installed.
- Publish positive, neutral and negative paired results. Actual billing and independent correctness grades are necessary for billed savings claims.
