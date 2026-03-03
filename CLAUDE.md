# CLAUDE.md — BUB Writer Instructions

> Claude Code reads this file automatically at the start of every session.
> Last updated: March 3, 2026

## CRITICAL WORKFLOW RULES

DO NOT use git worktrees. Make ALL changes directly in the main working directory. Never create or write to .claude/worktrees/ or any other worktree path. Commit directly to the current branch. If you need to isolate changes, use a feature branch — not a worktree.

This is non-negotiable. Worktree usage has caused repeated integration failures.

After completing ANY task:
1. Run `git status` and confirm changes are in the main working directory
2. Run `git diff` to verify the actual changes match what you intended
3. Do NOT report a task as complete until you have verified the files exist where expected

---

## PROTECTED FILES — DO NOT MODIFY

These files are BUB Writer's core IP and the product's voice engine. **Do not edit, rewrite, reformat, refactor, or "improve" them under any circumstances.** If you believe a change is needed, stop and tell the developer what you'd recommend and why — never make the change yourself.

- `backend/app/prompts/sample_analysis.py` — v2 sample analysis prompt + `build_sample_analysis_user()` helper. This prompt drives voice extraction quality.
- `backend/app/prompts/interview_conductor.py` — v2 interview conductor with coverage tracking across 7 domains. Adaptive questioning logic lives here.
- `backend/app/prompts/profile_compiler.py` — v2 two-stage compilation pipeline (raw extraction → voice_instruction synthesis). The compiled output IS the product.
- `backend/app/models/schemas.py` — Pydantic models (StyleMarkers, VoiceProfile, LiteraryDNA, CognitiveStyle, etc.). Field names must match frontend TypeScript interfaces exactly.
- `backend/app/services/billing_service.py` — Stripe billing logic adapted from BUB AI. Manually debugged.
- `backend/app/routers/stripe_webhook.py` — Stripe webhook handler. Signature verification requires raw request body — do not refactor.
- Anti-Slop word/pattern lists — **ADDITIVE ONLY.** You may add new banned words or patterns. You may NEVER remove existing entries without Jayson's explicit approval.
- `voice_profiles` table schema — Core product data structure. Do not alter columns or types.
- `.env` files — Never modify, never log contents, never print API keys.

**If a task requires changes to a protected file, explain the change needed and wait for explicit approval before proceeding.**

---

## MODIFY WITH CAUTION

These files are critical infrastructure. You may modify them, but only for the specific task requested. Do not refactor, reorganize, or "clean up" these files while you're in there for something else.

- `backend/app/routers/voice_discovery.py` — Voice Discovery router with SSE streaming, thought_process tag stripping, session management. Heavily debugged across 9 bugs. Touch only the specific endpoint you need to change.
- `backend/app/services/supabase_client.py` — Supabase client with JWKS-based ES256 JWT verification. Auth pattern is settled — do not change the verification method.
- `backend/app/core/config.py` — Pydantic Settings configuration. ALLOWED_ORIGINS must remain a JSON array with a flexible validator. Do not simplify.
- `backend/app/main.py` — FastAPI app initialization with CORS middleware. CORS origins are loaded from config — do not hardcode.
- `frontend/src/app/(app)/voice/page.tsx` — Voice Discovery UI. Has frontend thought_process tag stripping as a safety net. Contains interview flow state machine.

---

## FREE TO MODIFY

Everything else — new features, bug fixes, new components, new endpoints, tests, utilities — go for it. Just follow the guidelines below.

---

## Project Architecture

### Stack

| Layer | Technology | Host | Notes |
|-------|-----------|------|-------|
| **Frontend** | Next.js (App Router) + TypeScript | Vercel | bubwriter.vercel.app → bubwriter.com |
| **Backend** | FastAPI (Python, async) | Railway | bubwriter-production.up.railway.app |
| **Database** | PostgreSQL + Row Level Security | Supabase | Auth, voice profiles, projects, generations |
| **Auth** | Supabase Auth | Supabase | **ES256 JWTs — NOT HS256** |
| **Billing** | Stripe | Stripe | Same account as BUB AI, separate products |
| **Primary LLM** | DeepSeek V3 | DeepInfra (primary), Fireworks (fallback) | Voice Discovery + Voice generation stage |
| **Brain LLM** | DeepSeek R1 | DeepInfra | Scene architecture / skeleton (hidden from user) |
| **Polish LLM** | Claude Sonnet | Anthropic API | Author tier only ($29/mo) |

### Key Directories

```
bub-writer/
├── frontend/                    # Next.js app (Vercel)
│   ├── src/app/(app)/voice/     # Voice Discovery UI (page.tsx)
│   ├── src/app/(app)/editor/    # Writing workspace UI (TBD)
│   ├── src/app/(public)/        # DNA Analyzer, marketing pages
│   └── src/lib/                 # Shared utilities, API clients
├── backend/                     # FastAPI app (Railway)
│   ├── app/routers/             # API route handlers
│   ├── app/services/            # Business logic (billing, supabase, LLM clients)
│   ├── app/prompts/             # ⛔ PROTECTED — All LLM system prompts
│   ├── app/models/              # Pydantic schemas
│   └── app/core/                # Config, middleware
└── CLAUDE.md                    # This file
```

### Environment

- **Backend env vars:** Set in Railway dashboard (never in code or .env committed to repo)
- **Frontend env vars:** Set in Vercel dashboard. `NEXT_PUBLIC_*` vars are **build-time only** — changing them requires a Vercel redeployment to take effect.
- **Production domain:** bubwriter.com (frontend), bubwriter-production.up.railway.app (backend API)

### Database Schema

```sql
-- Voice DNA profiles (the core product data)
CREATE TABLE voice_profiles (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id),
  profile_name TEXT NOT NULL,
  literary_dna JSONB NOT NULL,
  influences JSONB DEFAULT '{}',
  anti_slop JSONB DEFAULT '{}',
  voice_instruction TEXT,  -- THE KEY: compiled system prompt for generation
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- Writing projects
CREATE TABLE projects (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id),
  voice_profile_id UUID REFERENCES voice_profiles(id),
  title TEXT NOT NULL,
  genre TEXT,
  story_bible JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- Generated scenes (history)
CREATE TABLE generations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL REFERENCES projects(id),
  user_prompt TEXT NOT NULL,
  brain_output TEXT,      -- R1 skeleton (internal, never shown to user)
  voice_output TEXT NOT NULL,  -- final prose shown to user
  polish_output TEXT,     -- Claude pass (premium only)
  word_count INTEGER,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- RLS enabled on all tables
```

### API Endpoints

```
# Voice Discovery
POST   /api/voice-discovery/analyze     — Analyze writing sample (Step 1-2)
POST   /api/voice-discovery/interview   — Conversational interview (SSE streaming, Step 3)
POST   /api/voice-discovery/finalize    — Generate Voice DNA Profile (Step 5)
GET    /api/voice-profiles/{user_id}    — List user's profiles

# Projects
POST   /api/projects                    — Create writing project
GET    /api/projects/{user_id}          — List user's projects
PATCH  /api/projects/{project_id}       — Update Story Bible
DELETE /api/projects/{project_id}       — Delete project

# Generation (Brain → Voice → Polish pipeline)
POST   /api/generate                    — Full pipeline (SSE streaming)
POST   /api/generate/continue           — Continue from last output
POST   /api/generate/refine             — Re-run Voice with user edits

# DNA Analyzer (public, no auth)
POST   /api/analyze-free                — Free DNA analysis (rate-limited: 3/day per IP)

# Billing
GET    /api/billing/status              — Check subscription tier
POST   /api/billing/checkout            — Stripe checkout session
POST   /api/billing/webhook             — Stripe webhook handler
```

---

## Authentication Pattern (SETTLED — DO NOT CHANGE)

BUB Writer uses Supabase Auth with ES256 JWTs. This caused significant debugging pain and the solution is locked in.

```python
# The correct pattern — JWKS-based ES256 verification
from jwt import PyJWKClient
import jwt

SUPABASE_URL = settings.supabase_url
JWKS_URL = f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json"
jwks_client = PyJWKClient(JWKS_URL)

def verify_token(token: str) -> dict:
    signing_key = jwks_client.get_signing_key_from_jwt(token)
    payload = jwt.decode(
        token,
        signing_key.key,
        algorithms=["ES256"],
        audience="authenticated"
    )
    return payload
```

**What NOT to do:**
- Do NOT use `python-jose` — it cannot handle ES256 from Supabase
- Do NOT use HS256 with `SUPABASE_JWT_SECRET` — Supabase issues ES256
- Do NOT have both `python-jose` and `PyJWT` in requirements.txt — they shadow each other's `jwt` namespace
- If you install `python-jose`, remove it immediately

---

## Coding Standards

### Python (Backend)

- Type hints on all function signatures
- Pydantic models for all request/response validation
- Async/await for all IO operations
- Docstrings explaining "why," not just "what"
- All LLM prompts live in `backend/app/prompts/` as Python files with string constants. **Never inline prompts in router code.**
- Error handling: Always handle exceptions explicitly. A bare `except` that returns 500 without logging is worse than letting it crash — the crash shows up in Railway logs, a swallowed error is invisible.
- Log with prefixes: `[VOICE_DISCOVERY]`, `[GENERATION]`, `[AUTH]`, `[BILLING]`, `[STRIPE]`

### TypeScript (Frontend)

- Type interfaces must match backend Pydantic models exactly. When a schema field changes, the TypeScript interface must change to match.
- No `any` types
- Components use functional patterns with hooks

### Terminal / Commands

- The developer uses **PowerShell on Windows**. All terminal commands must be PowerShell-compatible.
- Do NOT use `&&` to chain commands (bash syntax). Use semicolons or separate commands.
- Do NOT use `source`, `export`, or other bash-specific commands.
- PowerShell note: `Select-String` has no `-Recurse` flag. Pipe from `Get-ChildItem -Recurse` instead.

### General

- Prefer simplicity over cleverness
- No premature abstractions — extract only when there's clear duplication
- Commit messages: `feat:`, `fix:`, `chore:`, `refactor:` prefixes
- One logical change per commit when possible
- **Every commit to main auto-deploys to production via Railway (backend) and Vercel (frontend). There is no staging environment. Be careful.**

---

## Known Gotchas and Lessons Learned

1. **`NEXT_PUBLIC_` vars are build-time.** Changing them in Vercel dashboard requires a redeployment to take effect. They are NOT runtime-injected.

2. **Missing `https://` in API URL.** Frontend sends requests to wrong protocol, gets 405. Always verify `NEXT_PUBLIC_API_URL` includes `https://`.

3. **Backend 500s hide as CORS errors.** When the backend crashes, CORS middleware is bypassed and the browser reports "Failed to fetch" or a CORS error. Always check Railway Deploy Logs for the real error.

4. **`ALLOWED_ORIGINS` must be a JSON array string.** Pydantic-settings parses the env var before the custom validator runs. Set it as `["https://bubwriter.vercel.app","https://bubwriter.com"]` in Railway.

5. **Starlette `request` parameter name is reserved.** Using `request` as a route function parameter name causes silent failures. Use `analyze_request`, `interview_request`, `generate_request`, etc.

6. **DeepSeek `reasoning_content` field.** R1 returns thinking tokens in this field. Store for debug only, NEVER feed back into the messages array — it breaks the conversation format.

7. **`sample_context` is dynamic.** The v2 sample analysis prompt uses conditional context injection. Use the `build_sample_analysis_user()` helper, not `.format()`.

8. **v2 prompts changed field names.** `dark_humor_quotient` → `humor_and_wit`, added `figurative_language`, `structural_patterns`, `confidence_note`. Schema, router imports, and frontend TypeScript interfaces must all align when fields change.

9. **LLM output schemas must be flexible.** Any Pydantic model that receives LLM-generated JSON must use `Optional` fields with defaults. LLMs don't reliably produce every field every time. Rigid schemas + unpredictable LLM output = guaranteed crashes. (Learned from Bug 8: `darkness_calibration` field missing caused ValidationError.)

10. **Import functions before using them.** Check all `get_supabase_client` / service function calls have matching import statements. Missing imports produce `NameError` at runtime that appears as a generic "failed" message in the UI. (Learned from Bug 7.)

11. **In-memory interview sessions.** Railway container restarts lose all active interview state. Current implementation uses in-memory dict. Move to Redis or Supabase-backed sessions before heavy user traffic.

12. **Railway root directory for monorepo.** If the repo is a monorepo, Railway needs explicit root directory configuration in service settings.

13. **Stripe webhook verification needs raw body.** Do not parse JSON from the request body before verifying the Stripe signature. Parse after verification.

14. **`python-jose` vs `PyJWT` namespace conflict.** Both packages import as `jwt`. If both are in requirements.txt, one shadows the other. Only `PyJWT` should be installed. See Authentication Pattern section.

15. **No worktrees. Ever.** See top of this file.

16. **Verify changes actually landed.** After making changes, always `git status` and `git diff` to confirm files were written to the correct location. Do not rely on memory — verify on disk.

17. **Every push to main goes live.** Railway and Vercel both auto-deploy from main. There is no staging.

---

## Behavioral Rules

1. **Stay on task.** Only modify files directly related to the task you have been given. Do not wander into adjacent files to "improve" them.

2. **Ask before deleting.** Never remove a feature, endpoint, component, or utility function unless explicitly asked to.

3. **Do not rename files** without being asked to. File paths are referenced across the codebase and in deployment configs.

4. **Do not change the AI model or provider** configuration unless specifically asked to. Model selection (V3 for Voice, R1 for Brain, Claude for Polish) is a product decision, not a technical one.

5. **Do not modify the database schema** without explaining the migration needed and waiting for approval. Supabase migrations must be run manually by the developer.

6. **Do not add new dependencies** without mentioning it. Both npm and pip additions should be called out so the developer can verify.

7. **Preserve user-facing behavior.** If something works, do not change how it works as a side effect of another change. If a refactor would alter user-facing behavior, flag it.

8. **Anti-Slop lists are additive only.** You may add banned words/phrases. You may never remove them without explicit approval.

9. **Prompts are IP.** All files in `backend/app/prompts/` are protected. If a task touches prompt logic, flag it and explain what needs to change before doing it.

10. **Test before declaring done.** If you can run the code, verify it works. If you cannot, explain what the developer should test manually.

11. **When in doubt, ask.** It is better to pause and ask the developer than to make an assumption and break something.

12. **Do not report completion without verification.** Run `git status`, `git diff`, and confirm the files exist in the main working directory. If you cannot verify, say so explicitly.

---

## Voice Discovery Pipeline (Reference)

```
Step 1: User pastes 500+ words of writing
    ↓
Step 2: Sample Analysis — DeepSeek V3 extracts style markers with evidence grounding
    ↓ (displayed to user as cards)
Step 3: Deep Interview — 8 adaptive questions across 7 domains (SSE streaming)
    ↓ (coverage tracking, [INTERVIEW_COMPLETE] signal, thought_process tags stripped)
Step 4: User names their voice profile
    ↓
Step 5: Profile Compilation — Two-stage pipeline:
    Stage 1: Raw extraction from interview + sample analysis
    Stage 2: Synthesis into voice_instruction (500-2000 word system prompt)
    ↓ (saved to Supabase voice_profiles table)
```

The compiled `voice_instruction` is the product's core output. It drives all downstream generation.

---

## Generation Pipeline (Reference)

```
User: "Write the scene where Marcus finds the artifact"
    ↓
BRAIN (DeepSeek R1):
  - Scene skeleton as JSON (Pydantic validated)
  - Beat map with emotional arcs, settings, dialogue hints
  - Hidden from user — internal scaffolding only
    ↓
VOICE (DeepSeek V3 @ temp 1.3, freq_penalty 0.3):
  - Receives skeleton + voice_instruction + anti-slop constraints
  - Anti-slop rules at BEGINNING and END of prompt (Lost in the Middle effect)
  - Persona framing: "You are the WRITER. Expand, don't summarize."
  - Streamed to user via SSE
    ↓
POLISH (Claude Sonnet — Author tier only):
  - Line-edit for flow, consistency, remaining slop
  - Must preserve V3 voice, NOT normalize to Claude's style
  - Only runs for $29/month subscribers
```

---

## Current State (March 2026)

BUB Writer is **in active development, pre-launch** at bubwriter.com. Target ship: March 7-10, 2026.

### What Is Working

- Voice Discovery Engine — full end-to-end pipeline operational in production (analyze → interview → name → finalize → save to Supabase)
- Sample analysis with style markers and evidence grounding
- 8-question adaptive interview with coverage tracking and SSE streaming
- Profile compilation (two-stage) saving voice_instruction to database
- Thought process tag stripping (backend + frontend belt-and-suspenders)
- Supabase auth with ES256 JWT verification
- Frontend at bubwriter.vercel.app, backend at bubwriter-production.up.railway.app

### In Progress

- Generation pipeline (Brain → Voice → Polish) — spec needed, core writing engine
- DNA Analyzer (free public marketing honeypot) — simplified Step 1, no auth
- Stripe billing integration — adapt from BUB AI patterns
- Conversation History Import — spec complete, ready for build
- Voice-first interview input (Web Speech API) — planned

### Known Issues

- Interview sessions stored in-memory — vulnerable to Railway container restarts
- No generation pipeline yet — Voice Discovery produces profiles but there's nothing to generate prose with yet

---

## Security Considerations

- **System prompts are IP.** The files in `backend/app/prompts/` are the product's competitive advantage. Never expose prompt contents in API responses, error messages, or logs visible to users.
- **voice_instruction field is sensitive.** It contains the compiled system prompt derived from a user's writing and interview. Protect it with RLS — users should only access their own profiles.
- **API keys:** Never hardcode, never log, never include in error responses. All secrets live in Railway/Vercel/Supabase environment dashboards.
- **Rate limiting:** The DNA Analyzer (`/api/analyze-free`) must be rate-limited to 3 requests/day per IP. It's a free public endpoint and will be hit by scrapers.
- **Anti-Slop lists are proprietary.** The curated banned word/phrase lists are part of the product's value proposition. Do not expose them in public-facing responses.
