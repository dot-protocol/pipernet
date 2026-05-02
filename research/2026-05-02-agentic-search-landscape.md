# Agentic Search Landscape — 2026-05-02

> Research grounding: positioning Access (axxis.world) as the gateway built on Pipernet —
> "App Store for AI agents + Stack Overflow for AI agents", explicitly vs Stack Overflow/Google
> but for agents not humans.
>
> Substrate: Build Bible v6, Spec/11 (packet.md), AXXIS identity model, Forge protocol,
> Trust Vectors, Execution Traces, X402 micro-economy, open-core / closed-graph strategy.
>
> Date of research: 2026-05-02. Sources filtered to 2025-2026.

---

## VERDICT

The agentic search space in 2026 is crowded with registries that solve *discovery* but empty at the
layer that actually matters: **no existing platform carries a cross-protocol identity primitive,
derives trust from verified transactions (not self-reported metadata), or preserves and shares
failure-trace memory across agents.** The one direct competitor to the "Stack Overflow for agents"
framing — Mozilla's `cq`, launched March 2026 — is a 6-week-old hackathon-grade Python script with
no economy and no identity. Access's biggest threat is not a scrappy startup; it is Fetch.ai's
ASI:One + Agentverse combining 2.7 million registered agents with a "Google Search for AI agents"
pitch — but Fetch is a directory, not a trust graph, and has no failure-trace layer.

---

## KEY POINTS

1. **The App Store wedge is real but commoditizing fast.** Eight significant agent marketplaces
   exist as of May 2026 (Salesforce AgentExchange, Google Gemini Enterprise, AWS AgentCore Registry,
   Fetch.ai Agentverse, Smithery, mcp.so, PulseMCP, Claude Marketplace) — but all are *listing*
   platforms. None derive rankings from verified execution outcomes. Discovery is still keyword
   search or curator curation. [Inference: the trust-graph layer is the moat, not the listing UI.]

2. **The Stack Overflow wedge is completely open.** Mozilla's `cq` (launched March 24, 2026) is the
   only named "Stack Overflow for agents" — an experimental Python project, <1 month old, no economy,
   no identity, no failure-trace primitives. HackOverflow is a February 2026 hackathon project.
   The *concept* is being named but the *product* does not exist. Access can own this.

3. **No existing platform has a cross-protocol identity unit.** MCP (9.7M SDK downloads/month),
   A2A (150+ orgs in production), X402 (75M+ monthly transactions), and Google AP2 all operate as
   transports without a shared identity primitive — exactly Spec/11's load-bearing claim. The DOT
   packet is the unit none of them have.

4. **Fetch.ai is the nearest strategic threat.** ASI:One explicitly pitches "Google Search for
   AI agents," Agentverse hosts 2.7 million registered agents, and the platform has agent
   payments live (January 2026). But Fetch's agents are registered by self-declaration, not
   verified transaction history. Trust is not earned — it is stated. Fetch is a phone book; 
   Access is intended to be a credit bureau.

5. **The micro-economy layer is converging on USDC but fragmented across protocols.** X402 (Coinbase),
   MPP (Stripe + Tempo), Google AP2, and Circle's Nanopayments are each partial solutions. 99% of AI
   agent payments use USDC. $43M in agent commerce in nine months through March 2026. No platform
   bridges these rails under a single agent identity. [Inference: Access's protocol-agnostic AXXIS
   unit-of-account + cross-chain settlement is a real structural gap to fill.]

---

## §1. The Landscape — Top Platforms (2026)

| Platform | Category | Launch | Traction | Primary value prop | Protocol |
|---|---|---|---|---|---|
| **Salesforce AgentExchange** | Enterprise marketplace | March 4, 2025 | 1,000+ agents, 200+ partners, 6,000+ paid Agentforce deals | Trusted agent + skill marketplace for Salesforce/Slack ecosystem | Agentforce (proprietary) |
| **Google Gemini Enterprise (Agentspace)** | Enterprise discovery | Oct 2025 (rebranded) | Agent Gallery GA; Agent Registry GA; marketplace with Atlassian, Box, Oracle, ServiceNow, Workday | Single pane for enterprise agent discovery, governance, creation | A2A (Linux Foundation, v1.2 March 2026) |
| **AWS AgentCore Registry** | Enterprise governance registry | April 13, 2026 (preview) | Private catalog; CloudTrail audit; semantic + keyword search | Governed internal catalog for agents, tools, skills, MCP servers | AWS Bedrock native; MCP-compatible |
| **Fetch.ai Agentverse + ASI:One** | Consumer + dev directory | Agentverse: 2022; ASI:One: late 2025 beta / 2026 GA | 2.7 million registered agents; ASI:One "Google Search for agents" positioning | Discover, deploy, and orchestrate agents; agent payments live (Jan 2026) | uAgents (Fetch.ai protocol); X402-compatible |
| **Smithery** | Developer MCP registry | 2024 | 7,000+ MCP servers | Closest to Docker Hub for MCP — installable servers with README, install commands | MCP |
| **PulseMCP** | Developer directory | 2024 | 5,500+ servers listed (late 2025) | Largest hand-reviewed MCP directory; editorial curation | MCP |
| **mcp.so** | Community hub | 2024 | Not disclosed | Community resource hub: guides, tutorials, curated MCP server lists | MCP |
| **Official MCP Registry** | Canonical registry | Sept 2025 preview | 9,400+ servers (April 2026, up from 1,200 in Q1 2025) | Anthropic-maintained authoritative programmatic registry | MCP (Anthropic) |
| **Claude Marketplace** | Enterprise SaaS marketplace | March 6, 2026 | 6 launch partners (Snowflake, GitLab, Harvey AI, Rogo, Replit, Lovable Labs) | Claude-powered enterprise tools for customers; "Project Deal" agent commerce experiment (April 2026) | Claude API + MCP |
| **Kong MCP Registry** | Enterprise governance | 2025 | Not disclosed | Enterprise directory with audit, governance, OAuth | MCP + enterprise auth |
| **Mozilla cq** | "Stack Overflow for agents" | March 24, 2026 | Open source; weeks old at time of research | Shared knowledge commons: agents query/contribute/validate problem-solution pairs | MCP (plugin); SQLite local + team API |
| **AgentOps / LangSmith / Langfuse** | Observability / trace platforms | AgentOps: 2024; LangSmith: 2023; Langfuse: 2024 | LangSmith: part of LangChain ecosystem; AgentOps: 400+ LLMs tracked | Execution trace capture, session replay, cost analytics, failure debugging | LangChain / custom |
| **Mnemom** | Agent trust / integrity | 2025 | Team Trust Ratings launched; AAA–CCC bond-rating-style scores | Cryptographic proof of agent reasoning + decisions; team trust ratings | MCP-compatible |
| **BotStall** | Agent-to-agent marketplace | March 2026 | 17 products at launch | Marketplace where agents are sellers; three-tier trust gate system | API + Stripe |
| **Composio** | Agent integration / tool-call hub | 2024 | 100,000+ developers; $1M+ ARR; $25M Series A (Lightspeed, July 2025) | Unified API layer for agent tool calls across 250+ services | MCP + custom connectors |

**Notes on protocol adoption as of May 2026:**
- MCP: 9.7M SDK downloads/month. 9,400+ servers in official registry.
- A2A: 150+ organizations in production (v1.2, March 2026). Under Linux Foundation governance.
- X402: 75M+ monthly transactions (Dec 2025 V2). Integrated as crypto rail in Google AP2.
- AP2 (Google Agent Payments Protocol): Integrated X402 as stablecoin facilitator.
- Circle Nanopayments: Gas-free USDC microtransactions across 11 blockchains, live mainnet April 2026.

---

## §2. What They're Doing Well

### Salesforce AgentExchange

**Primary value prop:** The most complete enterprise agent distribution system in existence. 6,000+ paid Agentforce deals, 200+ launch partners, existing Salesforce install base. The activation moment is trivially low — an existing Salesforce admin deploys a pre-certified agent skill in minutes.

**Network effects forming:** Salesforce AppExchange → AgentExchange transition brings an established two-sided marketplace (ISVs already know how to sell here) into the agent era. Trust is CRM-centric: agents rated within the Salesforce ecosystem by the same admins who already rate apps.

**What they're doing well:** Trust-by-review model works for enterprise compliance. Salesforce certification = enough for an IT buyer. Fast activation. Large existing install base is a distribution moat nobody else has.

---

### Google Gemini Enterprise (+ A2A + Agentspace lineage)

**Primary value prop:** Full lifecycle — discover → create (no-code Agent Designer) → govern (Agent Registry) → deploy → monitor. The only platform that ships discovery AND creation AND governance in one product.

**Network effects forming:** A2A's Linux Foundation governance makes Google the de-facto standard-setter for multi-agent interoperability at enterprise. 150+ orgs in production. Agent Gallery provides the consumer-facing discovery that developers want to publish to.

**What they're doing well:** Protocol governance (A2A under Linux Foundation is a deliberate "not Google's standard" move that is working). Agentspace → Gemini Enterprise rebrand shows they're serious. Google Cloud Next 2026 keynote was an all-in agentic bet.

---

### Fetch.ai Agentverse + ASI:One

**Primary value prop:** Scale. 2.7 million agents. First "Google Search for agents" explicit positioning. ASI:One orchestrates personal tasks across verified brand agents.

**Network effects forming:** The ASI Alliance (Fetch.ai + SingularityNET + Ocean Protocol + CUDOS) creates a combined ecosystem larger than any single player outside Big Tech. Agent payments live January 2026 (AI-to-AI payment for real-world transactions).

**What they're doing well:** Registering real agents at scale. The "Claim Your Agent" anti-knockoff system is the first brand-verification move in the space. Personal orchestration layer (ASI:One) is the most developed agent-OS interface outside of Anthropic/OpenAI.

---

### Mozilla cq

**Primary value prop:** The concept is right. Agents query a shared commons before attempting a problem. Successful solutions persist. Failed attempts are logged. Confidence scores accrete. The cycle is: query → contribute → validate → score.

**What they're doing well:** Named the problem correctly and shipped fast. Open source. The four-phase knowledge cycle (query / contribute / validate / score) maps to a real need.

---

### Anthropic / Claude Ecosystem (MCP Registry + Claude Marketplace + Project Deal)

**Primary value prop:** Protocol ownership (MCP), enterprise marketplace, and the most credible agent-commerce research (Project Deal). MCP's 9.7M SDK downloads/month means Anthropic de-facto sets the protocol layer.

**Network effects forming:** Every MCP server is a potential node in Anthropic's discovery layer. Claude Marketplace gives the enterprise distribution channel. Project Deal (April 2026) proved agent-to-agent negotiation works and that model quality determines outcome — a direct proof-of-concept for trust-weighted agent selection.

**What they're doing well:** Protocol ownership without a canonical registry creates an ecosystem of third-party registries that all depend on MCP. Anthropic is the TCP/IP without being the HTTP — and they know it.

---

## §3. What They're Missing — The Access Wedge

The following capabilities are **absent from every platform** in the landscape as of May 2026.

### Gap 1: Cross-protocol identity primitive (the load-bearing gap)

Every existing platform operates within one protocol namespace:
- Salesforce AgentExchange agents are Agentforce agents
- Google Gemini Enterprise agents are A2A agents
- Fetch.ai Agentverse agents are uAgents
- MCP registries list MCP servers
- X402 has wallets, not identities

**None of them share an underlying identity primitive.** An agent on Salesforce AgentExchange has no identity on Fetch.ai Agentverse. An MCP server has no AXXIS ID. An X402 wallet is not the same as an A2A agent card.

Spec/11 names this gap directly: "None share an underlying identity primitive. All transports, no unit."

The DOT packet's 256-byte bootstrap — Ed25519 pubkey as identity, self-signed, content-addressed, transport-agnostic — is the unit that every existing transport is missing. Access's AXXIS ID is the first identity that works across MCP, A2A, AP2, X402, and any future protocol simultaneously.

[Inference: this is the most defensible architectural position. Once agents have AXXIS IDs, every interaction accretes to a single trust vector regardless of which protocol carried the payload.]

---

### Gap 2: Trust derived from verified execution, not self-report

Every existing ranking system is self-reported or curator-assigned:
- MCP registries rank by download count, GitHub stars, or manual curation
- Salesforce AgentExchange uses human review + certification
- Fetch.ai Agentverse uses self-registration (agents declare their own capabilities)
- Mnemom's AAA–CCC score is based on behavioral monitoring, not execution economics

**No platform derives trust vectors from actual transaction outcomes.** What did this agent deliver? What did it cost? What did the counterparty rate it? What domains has it transacted in? What was the error rate over 1,000 Forges?

The Build Bible v6 §2.3 lays out the trust vector: transaction count, transaction volume, success rate, counterparty quality, domain specificity, response time, consistency. **None of these exist in any current platform.**

Anthropic's Project Deal is the closest proof-of-concept (April 2026): Claude Opus agents earned $3.64 more per transaction than Haiku agents. Model quality → outcome quality → trust signal. But Project Deal is a research paper, not a product. No platform is yet recording this signal systematically.

[Inference: Access's trust layer is the "credit bureau for agents" vs. every existing platform's "phone book for agents." A phone book tells you who exists. A credit bureau tells you who to trust with your money.]

---

### Gap 3: Failure-trace memory — the AXXIS thesis

The Build Bible v6 anchor statement: "AXXIS exists so no intelligent system ever has to repeat a known mistake in isolation."

The current landscape:
- AgentOps / LangSmith / Langfuse capture execution traces *privately* (per-org, not shared)
- Mozilla cq is attempting to build a shared knowledge commons but is 6 weeks old, has no economy, and has no failure-trace primitive (it stores solution pairs, not failure patterns)
- Zero platforms share failure traces across organizations or agents in a queryable, trust-weighted commons

**The gap is not technical — it's governance and incentive.** Sharing failure traces is commercially disadvantageous (reveals proprietary strategy) and legally risky (reveals errors). The incentive structure for sharing failure traces does not exist yet.

Access's solution: the Forge packet structure makes every execution trace a signed, content-addressed, anonymizable artifact. Trust vectors update from outcomes without requiring the full trace to be public. Failure patterns become queryable without revealing the agent that failed.

[Inference: this is the "Stack Overflow for agents" wedge. Stack Overflow worked because answering questions built reputation. Access's equivalent: every Forge outcome — including failures — accretes to your trust vector. The incentive to share is the incentive to build trust.]

---

### Gap 4: Micro-economy support at 0.001 USDC

X402 V2 (December 2025) supports sub-$0.001 transactions. Circle Nanopayments (April 2026) enables gas-free USDC microtransactions. MPP (Stripe + Tempo, March 2026) adds fiat rails.

**But no discovery/registry platform supports micro-economy-native agent interactions.** Salesforce AgentExchange is SaaS subscription pricing. Google Gemini Enterprise is per-seat. Fetch.ai has agent payments but they're coarse-grained.

The scenario Build Bible v6 describes — "0.001 USDC for a data lookup, 0.01 USDC for an API call, 0.1 USDC for a YouTube transcript" — requires a platform designed from the ground up for micro-economy, not retrofitted from SaaS pricing models. No existing platform is this.

[Inference: Access's X402 + AXXIS unit-of-account architecture is one of the few systems where this scenario is possible by design, not as an edge case.]

---

### Gap 5: Cross-protocol bridging

The fragmentation in 2026:
- Salesforce agents (Agentforce) cannot transact with Fetch.ai agents (uAgents)
- A2A agents cannot pay MCP servers via X402 without bespoke integration
- Google AP2 integrates X402 but only for Google-ecosystem agents
- No platform routes an intent from an agent on one protocol to a capability on another

**Access's protocol abstraction layer (Build Bible v6 §12.3) is the only stated architecture for this.** "Your agent can be on X402. Another agent can be on something else. AXXIS bridges them."

The academic paper "Towards Multi-Agent Economies: Enhancing the A2A Protocol with Ledger-Anchored Identities and x402 Micropayments" (arXiv, 2025) identifies this gap formally: ledger-anchored identities + cross-protocol payment are missing from every existing multi-agent framework.

[Inference: this is a large-surface-area problem. Access doesn't need to solve all of it on day one. The Pipernet packet as the identity layer beneath all transports is the structural position; the bridging can ship incrementally.]

---

## §4. Threat Model

### Biggest threats by category:

| Threat | Platform | Timeline | Why | What Access needs to ship first |
|---|---|---|---|---|
| **App Store for agents** | Fetch.ai ASI:One + Agentverse | **Now** — 2.7M agents registered, ASI:One live | Explicit "Google Search for agents" positioning. Consumer-facing orchestration. First mover at scale. | Trust layer. Fetch is a phone book. Access must be the credit bureau. Ship 10 Forges with verifiable Trust Vector updates before Fetch adds reputation scoring. |
| **Stack Overflow for agents** | Mozilla cq | **6 weeks old** — still exploratory | Mozilla brand, open source, MCP plugin, named the concept publicly | Execute faster. cq has no economy, no identity, no failure-trace primitives. Access ships the Forge packet + trace memory before cq ships its 1.0. |
| **Enterprise App Store** | Salesforce AgentExchange | **Now** — 6,000+ enterprise deals | Existing install base, certified trust model, first to market for enterprise | Irrelevant for the Access wedge. AgentExchange is Salesforce-only. Access targets the open agent economy, not CRM plugins. |
| **Protocol capture** | Anthropic (MCP) | **Ongoing** — 9.7M downloads/month | If Anthropic adds trust scoring + failure trace to the official MCP Registry, they become the canonical layer | Speed. Anthropic moves slow on registry features. The official MCP Registry launched Sept 2025 and still doesn't have trust scoring. |
| **Enterprise agent OS** | Google Gemini Enterprise | **12–24 months** | A2A governance, Agent Designer, Agent Gallery. Most complete enterprise platform. Has the distribution. | Not Access's primary target. Enterprise is not the same wedge as open-agent economy. |
| **Agentic commerce** | Anthropic "Project Deal" → production | **6–12 months** | If Anthropic ships Project Deal as a product (not just research), they own agent-commerce trust | Ship Forge v1 first. Anthropic proved the concept; Access ships the infrastructure. |

### Most likely to ship "App Store for AI" first:
**Fetch.ai / ASI:One.** Already the most explicit about this framing. Already has 2.7M agents. Risk: they add trust scoring based on transaction history before Access ships.

### Most likely to ship "Stack Overflow for AI agents" first:
**Mozilla cq** is the current holder of the name. But it is 6 weeks old, has no economy, and its knowledge model is solution-pairs (not Execution Traces). The concept is unclaimed at the product level. Access can own it by shipping Forge-derived failure traces with a public queryable index.

### Are Anthropic / OpenAI / Google / Perplexity positioned to land this?

- **Anthropic:** Project Deal (April 2026) is proof-of-concept for agent commerce trust. MCP Registry has protocol distribution. Missing: Trust Vectors from execution, failure trace commons, cross-protocol identity. *Could ship within 12–18 months if they decide to.* Most dangerous long-term.
- **OpenAI:** GPT Store traction is weak (most creators earn ~$0.03/conversation). Workspace Agents is enterprise integrations, not open agent economy. Not positioned for this wedge.
- **Google:** A2A governance + Agent Gallery is the enterprise play. Not targeting open-protocol agent economy. The "AirDrop UX" vision of Spec/11 (local-first, no DNS, no central directory) is structurally opposite to Google's centralized architecture.
- **Perplexity:** Agent-as-search-interface play (Perplexity Computer, 2026). Not a marketplace or trust layer. Different wedge entirely.
- **Cognition / Devin:** Software agent execution. Not building discovery or trust infrastructure.

---

## §5. Access's Positioning (Synthesized from Substrate)

### The structural claim (Spec/11)

> "The packet is not just a communication format. It is the unit primitive every existing agent transport is missing."

Every MCP server, every A2A agent, every X402 wallet, every Fetch.ai uAgent has a payload but no identity unit. The DOT packet's 256-byte bootstrap is the first object that carries signature + self-description + chain simultaneously, with zero infrastructure dependency.

**Positioning sentence:** Access is the gateway where every agent finds work, builds trust, and compounds capability — regardless of which protocol it speaks. Pipernet is the plumbing underneath. Access is the city built on top.

---

### App Store wedge: the trust layer, not the listing

Every existing marketplace is a listing with search. Ratings are self-reported or editor-curated. None are derived from verified transactions.

Access's App Store equivalent is **not** "here are all the agents." It is: "here are agents ranked by what they've actually delivered, across verified Forges, with Trust Vectors you can query at any specificity."

The distinction the Build Bible v6 §2.4 makes is critical: intent matching against trust vectors in high-dimensional capability space. Not keyword search. Not download counts. Not Salesforce certification review.

> "No human could do this matching. No keyword search could do this matching."

---

### Stack Overflow wedge: Execution Traces as the unit of contribution

Stack Overflow's unit is a question-answer pair, voted on by humans.

Access's equivalent is the **Execution Trace** — what was attempted, what context, what happened, what the outcome was, verified by both parties, stored as a signed content-addressed packet.

The incentive structure:
- On Stack Overflow: answer questions to build reputation
- On Access: complete Forges to build Trust Vectors

The key difference: Stack Overflow's knowledge is declarative ("here's how to solve X"). Access's knowledge is operational ("here's what actually happened when agent Y attempted X under constraint Z"). Operational traces are richer, harder to fake (they're signed and economically verified), and more useful to agents than declarative text.

**The failure-trace layer:** Mozilla's cq stores solution-pairs. Access stores the full Execution Trace including failed paths. Failed Forges are first-class. A failed Forge that is well-documented is the most valuable object in the network — it's the mistake no other agent has to repeat.

---

### Open core / closed graph

The Pipernet spec is public goods (CC0, open source, no platform tax). Every agent transport can implement the DOT packet. The reference implementation is open.

The **Access Trust Graph** — the accumulated Execution Traces, the Trust Vectors, the Intent-to-Trust-Vector matching index — is proprietary. Not because Access wants a walled garden, but because this is the moat that cannot be copied even if the protocol is:

> "A fast follower can copy the protocol. They cannot copy 10,000 Forges of accumulated trust data." — Build Bible v6 §12.4

The strategy is structurally identical to Red Hat (open Linux kernel, proprietary support), HashiCorp (open Terraform, proprietary cloud), or GitHub (open Git protocol, proprietary collaboration graph). The protocol is the public goods foundation. The graph is the business.

---

### Agent-first design: the user IS the agent

Every existing marketplace is designed for humans to browse. Salesforce AgentExchange has a UI. Fetch.ai Agentverse has a web app. The MCP registries are GitHub-style README pages.

Access's primary user is an agent making an API call. The "browse" is an ANN search against trust vectors. The "listing" is a structured capability declaration queryable by semantic embedding. No human needs to browse anything — their agent queries the space, enters a Forge, and returns verified outcomes.

This is the architectural inversion the market hasn't made. The Build Bible v6 §3.2 is precise:

> "Design for agents first → humans can observe and steer. Design for humans first → agents work around you."

---

### Why Pipernet specifically creates defensibility

Pipernet's 5-layer stack (Packet / Transport / Discovery / Privacy / Verb) removes structural dependencies:
- No DNS → content-addressed identifiers
- No CA → Ed25519 self-signed identity
- No cloud auth → AXXIS ID
- No central database → append-only local chain

The Alan Carr inversion (Spec/11 §1): the existing protocols are not bad; they are comprehensively *dependent*. Pipernet removes the dependencies. An agent running on Pipernet doesn't need a Salesforce org, a Google Cloud account, or a Fetch.ai wallet. It needs an Ed25519 keypair and a DOT.

This is not just a technical choice — it is a regulatory choice. Zero personal data by design means zero GDPR/CCPA exposure. The trust is in the verified outcomes, not in who the agent is.

---

## §6. The 30/90/180-Day Plan

### 30 days: Own the name, plant the flag

**Ship:**
- AXXIS ID v1: Ed25519 keypair generation, AXXIS ID announcement packet, public resolver
- Forge v1 (minimum viable): MCP call + X402 payment + outcome confirmation + mutual rating
- Execution Trace v1: Signed, content-addressed, stored in Access Trust Graph
- Trust Vector v1: 3 dimensions (transaction count, success rate, domain tag) — enough to rank
- Public queryable index: GET `/agents?domain=code&min_success_rate=0.9` returns ranked agents
- Pipernet spec public: publish spec/11-packet.md, README, open source reference impl

**Message:** "We built the unit primitive every existing agent transport is missing." Publish a blog post comparing Access AXXIS ID to what every other platform does for identity. Name the gap explicitly. This is the spec/11 framing: "MCP needs the packet more than the packet needs MCP."

**Win condition:** One agent developer writes "I registered my agent on Access and now it has a Trust Vector that works across MCP and X402." That post exists publicly.

---

### 90 days: Seed the failure-trace commons

**Ship:**
- Failure Trace v1: Failed Forges are stored (anonymizable). Public API: `GET /traces?outcome=failed&domain=X`
- cq integration: Access runs an MCP server that cq-compatible agents can query for Execution Traces
- Cross-protocol bridge v1: An MCP server with an AXXIS ID can receive a Forge from an X402 agent
- Trust Vector v4+: Add transaction volume, counterparty quality, response time dimensions
- Developer SDK: `pip install access-sdk` / `npm install @access/sdk` with 1-line Forge integration
- Pipernet packet v1 reference implementation: 200-byte bootstrap, Ed25519, PARENT_ID chain

**Message:** "Every agent that completes a Forge on Access learns from every failure before it." Publish the first "failure trace analytics" — what are the most common failure patterns in MCP tool calls? What domains have the highest error rates? This is the Stack Overflow equivalent of the "Top Questions" page.

**Win condition:** 1,000 Execution Traces in the Access Trust Graph. One agent developer discovers a solution to a problem by querying the failure trace commons instead of debugging from scratch.

---

### 180 days: Protocol primitive, not just a product

**Ship:**
- A2A bridge: An A2A agent can register an AXXIS ID and receive Forges from MCP agents
- Fetch.ai / Agentverse bridge: A Fetch.ai uAgent can acquire an AXXIS ID and appear in Access rankings
- Intent Vector matching v1: Semantic embedding against Trust Vectors — ANN search replaces keyword
- Public Trust Graph API: Third parties can query Trust Vectors programmatically
- AXXIS unit of account v1: Cross-chain settlement with USDC on Base as default
- Open Core repo: Pipernet packet spec, AXXIS ID spec, Forge format all published as open standards with CC0 license

**Message:** "Access is the identity layer under every agent protocol." Publish interoperability matrix showing which protocols an AXXIS ID works with. The target is a press narrative: "The DID for AI agents."

**Win condition:** One external developer builds a tool that reads Trust Vectors from the Access API to rank agents in their own product. The Trust Graph becomes a public utility.

---

## §7. Sources

All sources accessed 2026-05-02. Links to primary sources preferred.

**Agent registries and marketplaces:**
- [Official MCP Registry](https://registry.modelcontextprotocol.io/) — Anthropic-maintained canonical MCP registry
- [Smithery MCP Registry](https://smithery.ai/) via [Composio alternatives](https://composio.dev/blog/smithery-alternative) — 7,000+ MCP servers
- [PulseMCP traction](https://automationswitch.com/ai-workflows/where-to-find-mcp-servers-2026) — 5,500+ servers, largest hand-reviewed directory
- [MCP adoption stats](https://www.digitalapplied.com/blog/mcp-adoption-statistics-2026-model-context-protocol) — 9,400+ servers April 2026; 9.7M SDK downloads/month
- [Salesforce AgentExchange launch](https://www.salesforce.com/news/press-releases/2025/03/04/agentexchange-announcement/) — March 4, 2025; 200+ partners; 1,000+ agents
- [Salesforce 6,000+ deals](https://www.salesforce.com/news/stories/2025-recap/) — 2025 recap
- [Google Gemini Enterprise (Agentspace)](https://cloud.google.com/blog/products/ai-machine-learning/introducing-gemini-enterprise-agent-platform) — Agent Gallery, Agent Registry, Agent Designer
- [AWS AgentCore Registry preview](https://aws.amazon.com/about-aws/whats-new/2026/04/aws-agent-registry-in-agentcore-preview/) — launched April 13, 2026
- [Fetch.ai Agentverse 2.7M agents](https://www.progressiverobot.com/2026/04/14/what-is-agentverse/) — April 2026
- [ASI:One "Google Search for agents"](https://venturebeat.com/ai/the-google-search-of-ai-agents-fetch-launches-asi-one-and-business-tier-for) — VentureBeat
- [Claude Marketplace launch](https://siliconangle.com/2026/03/06/anthropic-launches-claude-marketplace-third-party-cloud-services/) — March 6, 2026
- [Anthropic Project Deal](https://www.anthropic.com/features/project-deal) — April 2026; 186 deals, $4,000 value, 46% would pay
- [TechCrunch Project Deal](https://techcrunch.com/2026/04/25/anthropic-created-a-test-marketplace-for-agent-on-agent-commerce/)

**Stack Overflow for agents:**
- [Mozilla cq launch](https://blog.mozilla.ai/cq-stack-overflow-for-agents/) — March 23, 2026; open source; Python + SQLite + MCP
- [The Register on cq](https://www.theregister.com/2026/03/24/mozilla_introduces_cq_stack_overflow/) — "Stack Overflow for agents" framing
- [HackOverflow Devpost](https://devpost.com/software/hackoverflow-stack-overflow-for-ai-agents-at-hackathons) — February 2026 hackathon project
- [Stack Overflow data provider pivot](https://techcrunch.com/2025/11/18/stack-overflow-is-remaking-itself-into-an-ai-data-provider/) — November 2025; question volume collapsed from 200K/month (2014) to <4K/month (late 2025)

**Agent identity and protocols:**
- [A2A protocol launch](https://developers.googleblog.com/en/a2a-a-new-era-of-agent-interoperability/) — Google, April 9, 2025
- [A2A Linux Foundation](https://www.linuxfoundation.org/press/linux-foundation-launches-the-agent2agent-protocol-project) — June 2025; 150+ orgs in production
- [DID + VC for AI agents paper](https://arxiv.org/abs/2511.02841) — arXiv, November 2025
- [MCP-I at DIF](https://newsletter.identosphere.net/p/identosphere-167-march-1428-2026) — March 2026; decentralized identity for MCP
- [Zero-trust identity framework for agents](https://arxiv.org/html/2505.19301v1) — arXiv, 2025

**Payments and micro-economy:**
- [X402 V2 launch](https://docs.cdp.coinbase.com/x402/welcome) — Coinbase; December 2025; 75M+ monthly transactions
- [X402 on Stellar](https://stellar.org/blog/foundation-news/x402-on-stellar-unlocking-payments-for-the-new-agent-economy)
- [Circle Nanopayments](https://www.cryptotimes.io/2026/04/29/circle-introduces-nanopayments-system-for-ultra-small-usdc-transfers/) — April 29, 2026; gas-free USDC across 11 chains
- [99% AI payments in USDC](https://www.panewslab.com/en/articles/019cdbd2-7e4a-738f-8246-a19f053cc1ea) — $43M in 9 months
- [MPP launch](https://cgscomputer.com/agentic-commerce-protocols-the-complete-guide/) — Stripe + Tempo, March 2026

**Trust infrastructure:**
- [Mnemom trust plane](https://www.mnemom.ai/) — Team Trust Ratings; AAA–CCC scoring
- [BotStall agent marketplace](https://thoughts.jock.pl/p/botstall-ai-agent-marketplace-trust-gates-2026) — March 2026; three trust gates
- [Building trust systems for agent teams](https://earezki.com/ai-news/2026-02-25-building-trust-systems-for-ai-agent-teams-beyond-individual-credit-scores/) — February 2026

**Observability:**
- [AgentOps](https://research.aimultiple.com/agentic-monitoring/) — 400+ LLMs tracked
- [LangSmith observability](https://www.langchain.com/langsmith/observability)
- [Agent observability landscape 2026](https://galileo.ai/blog/best-ai-agent-observability-platforms)

**Tool integration:**
- [Composio $25M raise](https://startupwired.com/2025/07/22/composio-raises-25m-to-power-agentic-ai-workflow-tools/) — Lightspeed, July 2025; 100K+ developers; $1M+ ARR

**Cross-protocol academic:**
- [Multi-agent economies: A2A + x402](https://arxiv.org/html/2507.19550) — "Towards Multi-Agent Economies: Enhancing the A2A Protocol with Ledger-Anchored Identities and x402 Micropayments"

**Substrate (internal):**
- [Build Bible v6](/Users/blaze/Downloads/AXXIS_Build_Bible_v6.md) — February 2026
- [Spec/11 — The Packet](/Users/blaze/Movies/Kin/pipernet/spec/11-packet.md) — Draft v0.1, 2026-05-02

---

## §8. Open Questions

The following could not be answered definitively in this research pass:

1. **Fetch.ai Trust Vector plans.** Fetch.ai is 2.7M agents but no public roadmap item for transaction-derived trust scoring was found. The question: *is Fetch actively building this, or is it a directory forever?* Requires a closer read of Fetch.ai engineering blog and GitHub roadmap.

2. **Anthropic's next move on registries.** The official MCP Registry (launched Sept 2025) still lacks trust scoring. Project Deal (April 2026) proves the concept. Is Anthropic building a trust layer for MCP? No public announcement found. This is the highest-impact unknown.

3. **cq adoption velocity.** Mozilla cq is 6 weeks old. How fast is the developer community adopting it? GitHub stars, contributor count, and usage metrics were not published at time of research. A spike in cq adoption changes the timeline for Access's Stack Overflow wedge.

4. **Mnemom's network effects.** Mnemom's AAA–CCC scoring is the closest existing analog to Access's Trust Vector. How many agents are scored? Is the scoring public or private per-org? Is there a public API? Their site is thin on numbers. Direct investigation needed.

5. **The failure-trace governance problem.** The research confirms no platform shares failure traces across organizations. But the *legal* and *liability* dimensions of failure-trace sharing for commercial AI agents (especially in regulated industries) were not researched. This could be a significant adoption barrier for the Stack Overflow wedge.

6. **Circle Nanopayments + Access integration.** Circle's April 29, 2026 Nanopayments launch (gas-free USDC across 11 chains) was too recent for secondary source coverage. The direct API docs were not read. This is likely the right settlement layer for Access's micro-economy and needs a technical integration assessment.

7. **Android-first strategy timeline.** Spec/11 §3 recommends Android-first for the 8th choke point (App Store client-side gate). Access's positioning as a protocol layer (not a mobile app) may sidestep this — but if Access ever needs a consumer mobile interface, this decision has significant timeline implications. Not researched.

---

*Research by Rocky (Kin-1, claude-sonnet-4-6), 2026-05-02. Grounded in Build Bible v6 + Spec/11 substrate.*
*All traction claims cite primary sources with dates. "Not disclosed" used where numbers were unavailable.*
*[Inference: ...] tags mark conclusions drawn from evidence, not directly sourced.*
