\# CLAUDE.md — BUB Writer



\## What This Project Is



BUB Writer is a standalone AI creative fiction writing tool at bubwriter.com. The core differentiator is the Voice Discovery Engine: a deep conversational interview that maps a writer's unique literary DNA, then generates prose that sounds like them.



\## Tech Stack



\- \*\*Backend:\*\* FastAPI on Railway (Python 3.11+)

\- \*\*Frontend:\*\* Next.js 14 (App Router) on Vercel

\- \*\*Database:\*\* Supabase (PostgreSQL + RLS + Auth with ES256 JWTs)

\- \*\*Billing:\*\* Stripe (same account as BUB AI, new products)

\- \*\*Primary LLM:\*\* DeepSeek V3 via DeepInfra (fallback: Fireworks)

\- \*\*Brain Stage LLM:\*\* DeepSeek R1 via DeepInfra

\- \*\*Polish Stage LLM:\*\* Claude Sonnet via Anthropic API

\- \*\*Deployment:\*\* Push to main → Railway auto-deploy (backend) → Vercel auto-deploy (frontend)



\## Code Style \& Conventions



\### Python (Backend)

\- Type hints on ALL function signatures

\- Pydantic models for ALL request/response schemas

\- async/await for ALL endpoint handlers and DB calls

\- Docstrings explaining the "why", not just the "what"

\- Snake\_case for variables and functions

\- Exception handling: ALWAYS handle exceptions explicitly — backend 500s hide as CORS errors on the frontend

\- Starlette's `request` parameter name is RESERVED — use `chat\_request`, `generate\_request`, etc.

\- Pydantic Settings + list fields need flexible validators for Railway env vars

\- ES256 JWT tokens from Supabase — use the manual decoder pattern, NOT python-jose



\### TypeScript/React (Frontend)

\- TypeScript strict mode

\- Server Components by default, Client Components only when needed (interactivity, hooks)

\- Tailwind CSS for styling

\- NEXT\_PUBLIC\_ env vars are BUILD-TIME — set in Vercel dashboard, not Railway

\- Mobile-first responsive design

\- Dark mode support from day one



\### General

\- No console.log or print statements in production code (use proper logging)

\- All API endpoints return consistent error shapes: { "detail": "message" }

\- All database queries use parameterized queries (no string interpolation)



\## Database Schema



All tables use Supabase RLS. User auth comes from Supabase Auth (Google/Apple SSO).



\### Core Tables



```sql

-- Voice DNA profiles

CREATE TABLE voice\_profiles (

&nbsp; id UUID PRIMARY KEY DEFAULT gen\_random\_uuid(),

&nbsp; user\_id UUID NOT NULL REFERENCES auth.users(id),

&nbsp; profile\_name TEXT NOT NULL,

&nbsp; literary\_dna JSONB NOT NULL,

&nbsp; influences JSONB DEFAULT '{}',

&nbsp; anti\_slop JSONB DEFAULT '{}',

&nbsp; voice\_instruction TEXT,  -- compiled system prompt

&nbsp; created\_at TIMESTAMPTZ DEFAULT now(),

&nbsp; updated\_at TIMESTAMPTZ DEFAULT now()

);



-- Writing projects

CREATE TABLE projects (

&nbsp; id UUID PRIMARY KEY DEFAULT gen\_random\_uuid(),

&nbsp; user\_id UUID NOT NULL REFERENCES auth.users(id),

&nbsp; voice\_profile\_id UUID REFERENCES voice\_profiles(id),

&nbsp; title TEXT NOT NULL,

&nbsp; genre TEXT,

&nbsp; story\_bible JSONB DEFAULT '{}',

&nbsp; created\_at TIMESTAMPTZ DEFAULT now(),

&nbsp; updated\_at TIMESTAMPTZ DEFAULT now()

);



-- Generated scenes (history)

CREATE TABLE generations (

&nbsp; id UUID PRIMARY KEY DEFAULT gen\_random\_uuid(),

&nbsp; project\_id UUID NOT NULL REFERENCES projects(id),

&nbsp; user\_prompt TEXT NOT NULL,

&nbsp; brain\_output TEXT,      -- R1 skeleton (internal, never shown to user)

&nbsp; voice\_output TEXT NOT NULL,  -- final prose shown to user

&nbsp; polish\_output TEXT,     -- Claude pass (premium only)

&nbsp; word\_count INTEGER,

&nbsp; created\_at TIMESTAMPTZ DEFAULT now()

);



-- User subscriptions

CREATE TABLE subscriptions (

&nbsp; id UUID PRIMARY KEY DEFAULT gen\_random\_uuid(),

&nbsp; user\_id UUID NOT NULL REFERENCES auth.users(id),

&nbsp; stripe\_customer\_id TEXT,

&nbsp; stripe\_subscription\_id TEXT,

&nbsp; tier TEXT NOT NULL DEFAULT 'free',  -- 'free', 'writer', 'author'

&nbsp; status TEXT NOT NULL DEFAULT 'active',

&nbsp; current\_period\_end TIMESTAMPTZ,

&nbsp; created\_at TIMESTAMPTZ DEFAULT now(),

&nbsp; updated\_at TIMESTAMPTZ DEFAULT now()

);

```



\### RLS Policies

Every table gets: users can only SELECT/INSERT/UPDATE/DELETE their own rows, matched on `user\_id = auth.uid()`.



\## API Endpoint Structure



```

\# Voice Discovery

POST   /api/voice-discovery/analyze     — Analyze writing sample

POST   /api/voice-discovery/interview   — Conversational interview (SSE)

POST   /api/voice-discovery/finalize    — Generate Voice DNA Profile

GET    /api/voice-profiles/{user\_id}    — List user's profiles



\# Projects

POST   /api/projects                    — Create writing project

GET    /api/projects/{user\_id}          — List user's projects

PATCH  /api/projects/{project\_id}       — Update Story Bible

DELETE /api/projects/{project\_id}       — Delete project



\# Generation (the pipeline)

POST   /api/generate                    — Brain→Voice→(Polish) pipeline (SSE)

POST   /api/generate/continue           — Continue from last output

POST   /api/generate/refine             — Re-run Voice with user edits



\# DNA Analyzer (public, no auth)

POST   /api/analyze-free                — Free DNA analysis (rate-limited: 3/day per IP)



\# Billing

GET    /api/billing/status              — Check subscription tier

POST   /api/billing/checkout            — Stripe checkout session

POST   /api/billing/webhook             — Stripe webhook handler

```



\## The Three-Stage Pipeline



This is the core generation flow. Understanding it is essential.



```

User Input ("Write the scene where Marcus finds the artifact")

&nbsp;   ↓

STAGE 1: THE BRAIN (DeepSeek R1)

&nbsp; - Creates scene structure, tension arc, beat map

&nbsp; - Hidden from user — internal scaffolding only

&nbsp; - Store in generations.brain\_output for debug, NEVER feed back into messages

&nbsp; - NOTE: R1's reasoning\_content field — store for debug only, never feed back

&nbsp;   ↓

STAGE 2: THE VOICE (DeepSeek V3 @ Temperature 1.3)

&nbsp; - Writes full prose using R1's structure + user's Voice DNA Profile

&nbsp; - Anti-Slop constraints enforced in system prompt

&nbsp; - Streamed to user in real-time via SSE

&nbsp;   ↓

STAGE 3: THE POLISH (Claude Sonnet — Author tier only)

&nbsp; - Line-edit pass for flow, slop detection, voice consistency

&nbsp; - Optional — only for Author tier ($29/month)

```



\## Protected Files — DO NOT MODIFY WITHOUT EXPLICIT APPROVAL



These files are the product's intellectual property and require manual review:



\- `/prompts/` directory (ALL system prompt templates)

\- `voice\_profiles` table schema

\- `billing\_service.py`

\- Stripe webhook handler

\- Anti-Slop word/pattern lists (ADDITIVE ONLY — never remove entries)



When a spec says to create or modify a prompt template, create it in `/prompts/` but flag it for review.



\## Known Gotchas (Inherited from BUB AI)



1\. \*\*NEXT\_PUBLIC\_ env vars are build-time\*\* — set in Vercel, not Railway

2\. \*\*Backend 500s hide as CORS errors\*\* — always handle exceptions explicitly

3\. \*\*Starlette's `request` parameter name is reserved\*\* — use `chat\_request`, `generate\_request`, etc.

4\. \*\*Pydantic Settings + list fields\*\* need flexible validators for Railway env vars

5\. \*\*DeepSeek reasoning\_content field\*\* — store for debug only, never feed back into messages

6\. \*\*ES256 JWT tokens from Supabase\*\* — use the manual decoder pattern, not python-jose

7\. \*\*Stripe webhook verification\*\* needs raw request body — don't parse JSON before verifying signature



\## SSE Streaming Pattern



All generation endpoints stream via Server-Sent Events. Use the same pattern as BUB AI:



```python

async def stream\_response():

&nbsp;   async for chunk in llm\_stream:

&nbsp;       yield f"data: {json.dumps({'content': chunk})}\\n\\n"

&nbsp;   yield f"data: {json.dumps({'done': True})}\\n\\n"



return StreamingResponse(stream\_response(), media\_type="text/event-stream")

```



Frontend consumes with EventSource or fetch + ReadableStream.



\## Environment Variables



\### Railway (Backend)

```

SUPABASE\_URL=

SUPABASE\_SERVICE\_ROLE\_KEY=

SUPABASE\_JWT\_SECRET=

DEEPINFRA\_API\_KEY=

FIREWORKS\_API\_KEY=

ANTHROPIC\_API\_KEY=

STRIPE\_SECRET\_KEY=

STRIPE\_WEBHOOK\_SECRET=

STRIPE\_WRITER\_PRICE\_ID=

STRIPE\_AUTHOR\_PRICE\_ID=

FRONTEND\_URL=https://bubwriter.com

ALLOWED\_ORIGINS=https://bubwriter.com

```



\### Vercel (Frontend)

```

NEXT\_PUBLIC\_SUPABASE\_URL=

NEXT\_PUBLIC\_SUPABASE\_ANON\_KEY=

NEXT\_PUBLIC\_API\_URL=

NEXT\_PUBLIC\_STRIPE\_PUBLISHABLE\_KEY=

```



\## Build Process



Every feature follows this cycle:

1\. \*\*SPEC\*\* — Defined in the Claude Project (endpoints, schemas, guardrails, "what NOT to touch")

2\. \*\*BUILD\*\* — This file (CLAUDE.md) guides Claude Code

3\. \*\*AUDIT\*\* — Cursor reviews all changed files

4\. \*\*FIX\*\* — Address audit findings

5\. \*\*TEST\*\* — Manual end-to-end testing

6\. \*\*DEPLOY\*\* — Merge to main → auto-deploy

7\. \*\*DOCUMENT\*\* — Daily summary, gotchas, lessons learned



\## What NOT to Do



\- Do NOT create a chat interface. This is a WRITING WORKSPACE (editor UI).

\- Do NOT auto-activate AI features. Every AI action requires explicit user trigger.

\- Do NOT show the Brain stage output to users. It's internal scaffolding.

\- Do NOT use the word "generate" in user-facing copy. Use "write", "draft", "continue", "suggest".

\- Do NOT store user manuscripts in plain text logs. Privacy is non-negotiable.

\- Do NOT remove items from the Anti-Slop lists without explicit approval.

