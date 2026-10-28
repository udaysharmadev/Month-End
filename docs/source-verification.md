# Source verification record

Registry version: `2026-10-28.1`. Reviewed on 28 October 2026. All entries from the supplied PRD source register were checked for identity and bounded relevance. An unavailable original article is explicitly replaced by current official guidance; no paper experiments or Month End model savings were independently reproduced.

The [machine-readable register](source-register.json) records source IDs, review scope, status and mechanism mappings. Recheck changing sources before each release or within 90 days, whichever comes first. This is a maintained review process, not a background network monitor.

| ID | Source | Review status and scope |
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
| S11 | [LLMLingua: Compressing Prompts for Accelerated Inference of Large Language Models](https://aclanthology.org/2023.emnlp-main.825/) | abstract reviewed: Task-specific prompt compression; does not establish safe exact-code compression. |
| S12 | [LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression](https://aclanthology.org/2024.acl-long.91/) | abstract reviewed: Long-context task performance and compression under its evaluated conditions. |
| S13 | [LLMLingua-2: Data Distillation for Efficient and Faithful Task-Agnostic Prompt Compression](https://aclanthology.org/2024.findings-acl.57/) | abstract reviewed: Extractive prompt compression; transfer to exact source editing is unproven. |
| S14 | [Lost in the Middle: How Language Models Use Long Contexts](https://aclanthology.org/2024.tacl-1.9/) | abstract reviewed: Placement-sensitive retrieval in the tested tasks and models. |
| S15 | [Token Reduction Is Not Cost Reduction](https://arxiv.org/abs/2607.12161v5) | abstract reviewed: Reports a counterexample to equating delivered token reduction with billed savings. |
| S16 | [SkillReducer: Optimizing LLM Agent Skills for Token Efficiency](https://arxiv.org/abs/2603.29919v2) | abstract reviewed: Instruction/routing overhead and progressive-disclosure optimization in its sample. |
| S17 | [SWE-Skills-Bench: Do Agent Skills Actually Help in Real-World Software Engineering?](https://arxiv.org/abs/2603.15401v2) | abstract reviewed: Most sampled skills did not significantly improve outcomes; avoid broad universal claims. |
| S18 | [TokenEconomizer: Experience-Driven Black-Box Cost Control for Coding Agents](https://arxiv.org/abs/2610.22732v1) | abstract reviewed: Adaptive external-controller results under its own tested conditions. |
| S19 | [An Empirical Cost Attribution of Context-Compression Gateways in Multi-Turn Coding Agents](https://arxiv.org/abs/2609.22114v1) | abstract reviewed: Separates tool-schema filtering, content compression and history summarization. |
| S20 | [RTK](https://github.com/rtk-ai/rtk) | identity reviewed: Repository identity and stated command-output proxy purpose; claims not independently reproduced. |
| S21 | [Token Saver](https://www.skills.sh/otnc/skills_ai-agent-saving-tech/token-saver) | identity reviewed: Agent-neutral lean-work skill and setup audit; not causal performance evidence. |
| S22 | [Agent Skills for Context Engineering](https://github.com/muratcankoylan/Agent-Skills-for-Context-Engineering) | identity reviewed: Collection and modular-reference structure; no independent outcome validation. |
| S23 | [Anthropic Skills](https://github.com/anthropics/skills) | identity reviewed: Public skill-package examples; repository identity verified. |
| S24 | [Vercel Skills CLI](https://github.com/vercel-labs/skills) | identity reviewed: Installer/distribution tooling; Month End remote install remains pending publication. |
| S25 | [Superpowers](https://github.com/obra/superpowers) | identity reviewed: Skill/workflow framework; ergonomics reference, not proof of savings. |
| S26 | [Everything Claude Code / ECC](https://github.com/affaan-m/ECC) | identity reviewed: Multi-host harness/skill project; no claims independently reproduced here. |
| S27 | [I saved 10M tokens (89%) on my Claude Code sessions with a CLI proxy](https://www.reddit.com/r/ClaudeAI/comments/1r2tt7q/i_saved_10m_tokens_89_on_my_claude_code_sessions/) | anecdote reviewed: Author self-report; local output/usage figures do not establish billed cost per successful task. |
| S28 | [I benchmarked 5 token saving tools across Codex and Claude code](https://www.reddit.com/r/ClaudeAI/comments/1viyokr/i_benchmarked_5_token_saving_tools_across_codex/) | anecdote reviewed: Community comparison with disclosed competitive involvement; not an independent Month End evaluation. |
| S29 | [Rethinking skills and prompts for GPT-6 Astra](https://developers.openai.com/blog/rethinking-skills-and-prompts-for-gpt-6-astra) | verified: Scoped descriptions and progressive disclosure; model-specific advice is not universal. |
| S30 | [Antigravity agent skills](https://antigravity.google/docs/skills?tab=ide) | verified: Project skill path and progressive disclosure; global paths differ by surface. |
| S31 | [Skills in OpenAI API](https://developers.openai.com/api/docs/guides/tools-skills) | verified: Skill package/API integration boundaries; no changes made to host API settings. |
| C01 | [I cut Codex token usage about 50% with one AGENTS.md rule](https://www.reddit.com/r/codex/comments/1t6iulo/i_cut_codex_token_usage_50_with_one_agentsmd_rule/) | anecdote reviewed: Single huge-line hazard is a useful fixture idea. The post also suggests skipping checks; Month End does not adopt that rule or validate its percentage. |
| A01 | [Manage costs effectively](https://code.claude.com/docs/en/costs) | verified: Current official replacement for unavailable S01: context inspection, task boundaries and compaction. |

## Corrections and boundaries

- S01 could not be retrieved. A01 supplies current official Claude Code context/cost guidance; the unavailable article is not used as required evidence.
- S02 now resolves to the official research path. S30 redirects to the current consolidated Antigravity skills page; both canonical destinations are recorded.
- S16 and S17 were reviewed at their currently exposed v2 revisions. S15, S18 and S19 are pinned to the reviewed revisions. Preprint status is retained.
- Community pages were accessible, but headline percentages remain self-reports rather than Month End evidence. C01 is used only to motivate the huge-line regression fixture, not to justify skipping checks or changing proprietary prompts.
- Competitive repositories were identified; code, releases, security and efficacy were not independently audited. Their stars, installs and marketing headlines are not product measurements.
- The original DOCX remains an unchanged historical research artifact. This record updates source verification without rewriting that supplied document.
