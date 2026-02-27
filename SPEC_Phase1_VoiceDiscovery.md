# SPEC: Phase 1 — Voice Discovery Engine

**Sprint Days:** 2–4 (3 days)
**Depends on:** Phase 0 scaffolding (complete)
**Goal:** A writer pastes a writing sample, goes through a conversational AI interview, and gets a stored Voice DNA Profile that will drive all future prose generation.

---

## What This Phase Builds

The Voice Discovery Engine is the product's moat. It has three stages:

1. **Sample Analysis** — User pastes 500+ words of their writing. The AI analyzes it for style markers.
2. **Conversational Interview** — 7–10 adaptive questions that probe cognitive style, influences, anti-preferences, and creative process. Each question adapts based on prior answers AND the sample analysis.
3. **Profile Compilation** — All data synthesizes into a Voice DNA Profile (structured JSONB) and a compiled `voice_instruction` (the system prompt that drives the Voice stage in generation).

The interview is the product demo. If this feels magical, everything else is plumbing.

---

## Architecture Overview

```
User pastes writing sample (500+ words)
    ↓
POST /api/voice-discovery/analyze
    → DeepSeek V3 analyzes sample
    → Returns style_markers JSON
    ↓
User enters conversational interview
    ↓
POST /api/voice-discovery/interview (SSE streaming)
    → DeepSeek V3 conducts adaptive interview
    → Each exchange: user answer in, AI follow-up out
    → Interview state maintained server-side (in-memory dict keyed by session_id)
    → After 7-10 exchanges, AI signals interview complete
    ↓
POST /api/voice-discovery/finalize
    → Takes session_id + style_markers + interview_transcript
    → DeepSeek V3 compiles the full Voice DNA Profile
    → Generates the voice_instruction system prompt (500-2000 words)
    → Stores in voice_profiles table
    → Returns the profile to the user
```

---

## Backend Implementation

### 1. Writing Sample Analysis

**Endpoint:** `POST /api/voice-discovery/analyze`
**Auth:** Required (JWT)
**Request Body:**
```json
{
  "writing_sample": "string (500+ words of user's writing)",
  "sample_context": "optional string — what this sample is from"
}
```

**Validation:**
- `writing_sample` must be >= 500 words (split on whitespace, count)
- `writing_sample` must be <= 10,000 words
- Return 400 if too short with message: "Please provide at least 500 words for accurate analysis."

**Processing:**
- Call DeepSeek V3 via the LLM service with the analysis prompt (see Prompts section below)
- Parse the structured JSON response
- Return style markers to the frontend

**Response:**
```json
{
  "session_id": "uuid — generated server-side, used to track this voice discovery session",
  "style_markers": {
    "vocabulary_tier": "string — e.g., 'Literary-Accessible', 'Vernacular-Rich', 'Sparse-Precise'",
    "avg_sentence_length": "string — e.g., 'Short (8-12 words)', 'Medium (13-18)', 'Long (19+)'",
    "sentence_variety": "string — e.g., 'High rhythmic variation', 'Consistent cadence'",
    "pacing_style": "string — e.g., 'Escalation with breath', 'Steady accumulation'",
    "emotional_register": "string — e.g., 'Controlled intensity', 'Raw and unfiltered'",
    "sensory_preference": "string — e.g., 'Visual-dominant', 'Kinesthetic', 'Auditory'",
    "dialogue_style": "string — e.g., 'Sparse and loaded', 'Naturalistic', 'Stylized'",
    "pov_tendency": "string — e.g., 'Close third', 'First person intimate', 'Omniscient'",
    "tense_preference": "string — e.g., 'Past tense', 'Present tense', 'Mixed'",
    "dark_humor_quotient": "string — e.g., 'Present and dry', 'Absent', 'Pervasive'",
    "notable_patterns": ["array of 3-5 specific observations about THIS writer's unique patterns"],
    "comparable_authors": ["array of 2-3 authors whose style shares elements — be specific about WHAT element"]
  }
}
```

**Server-side session storage:**
- Create an in-memory dict: `voice_sessions: dict[str, VoiceSession]`
- `VoiceSession` is a dataclass/Pydantic model holding: `session_id`, `user_id`, `writing_sample`, `style_markers`, `interview_messages` (list of dicts), `created_at`
- Sessions expire after 2 hours (background cleanup task or TTL check on access)
- This is intentionally in-memory for MVP. Post-launch, migrate to Redis or Supabase if needed.

---

### 2. Conversational Interview

**Endpoint:** `POST /api/voice-discovery/interview`
**Auth:** Required (JWT)
**Streaming:** SSE (Server-Sent Events)
**Request Body:**
```json
{
  "session_id": "string — from the analyze step",
  "user_message": "string — the user's answer to the current question (empty string for first call to start the interview)"
}
```

**Validation:**
- `session_id` must exist in `voice_sessions` and belong to the authenticated user
- Return 404 if session not found or expired

**Processing:**
- Look up the session from `voice_sessions`
- If `user_message` is empty and `interview_messages` is empty, this is the START of the interview
- Append `user_message` to `interview_messages` (if not empty)
- Build the full conversation history for DeepSeek V3:
  - System prompt: The Interview Conductor prompt (see Prompts section)
  - Include `style_markers` in the system prompt so the interviewer knows what the sample revealed
  - Include all prior `interview_messages` as the conversation history
- Stream the AI's response via SSE
- As the response streams, also capture it server-side
- When streaming completes, append the AI response to `interview_messages`
- The AI's response includes a hidden signal when the interview is complete: the string `[INTERVIEW_COMPLETE]` at the very end (stripped before sending to frontend)

**SSE Format:**
```
data: {"type": "token", "content": "So "}
data: {"type": "token", "content": "tell "}
data: {"type": "token", "content": "me..."}
data: {"type": "done", "interview_complete": false, "question_number": 3}
```

When the interview is complete:
```
data: {"type": "done", "interview_complete": true, "question_number": 8}
```

**Interview Flow (7-10 questions):**

The AI conducts the interview adaptively. It does NOT follow a rigid script — it responds naturally to what the writer says and follows interesting threads. However, it must cover these diagnostic areas:

1. **Worldview & Identity** (Q1-2): "Is the world fundamentally funny, tragic, absurd, or beautiful?" / "What question are you always trying to answer in your writing?"
2. **Sensory Processing** (Q3): "When you're writing a scene and trying to bring it to life, where do you start — seeing it, hearing it, feeling the textures, or thinking about what needs to happen?"
3. **Process & Structure** (Q4-5): "How much do you know about your story before you start?" / "When you're stuck, what do you do?"
4. **Anti-Preferences** (Q6-7): "What kind of prose makes you cringe?" / "What writing advice do you violently disagree with?"
5. **Influences** (Q8): "Name 2-3 writers who shaped how you write — and for each, what did you absorb and what did you reject?"
6. **The Killer Question** (Q9-10): Follow-up based on the most interesting thing the writer revealed. This is where the magic happens — the AI notices something specific and probes deeper.

The AI should be warm, specific, and demonstrate that it's actually listening. It should reference the writer's sample analysis naturally ("I noticed in your sample that your dialogue carries a lot of weight without attribution tags — tell me more about that").

---

### 3. Profile Compilation

**Endpoint:** `POST /api/voice-discovery/finalize`
**Auth:** Required (JWT)
**Request Body:**
```json
{
  "session_id": "string",
  "profile_name": "string — user-chosen name for this voice profile, e.g., 'My Fiction Voice'"
}
```

**Validation:**
- Session must exist, belong to user, and have `interview_complete` = true (at least 7 exchanges)
- `profile_name` must be non-empty, max 100 chars

**Processing:**
- Gather: `writing_sample`, `style_markers`, full `interview_messages` transcript
- Call DeepSeek V3 with the Profile Compiler prompt (see Prompts section)
- Parse the structured response into the Voice DNA Profile
- Generate the `voice_instruction` — the compiled system prompt (500-2000 words)
- Store in `voice_profiles` table via Supabase
- Clean up the session from `voice_sessions`
- Return the complete profile

**Response:**
```json
{
  "profile_id": "uuid",
  "profile_name": "string",
  "literary_dna": {
    "vocabulary_tier": "string",
    "sentence_rhythm": "string",
    "pacing_style": "string",
    "emotional_register": "string",
    "sensory_mode": "string",
    "dialogue_approach": "string",
    "pov_preference": "string",
    "tense_preference": "string",
    "humor_style": "string",
    "darkness_calibration": "string",
    "cognitive_style": {
      "processing_mode": "string — visual/verbal/abstract/concrete",
      "story_entry_point": "string — character/world/conflict first",
      "revision_pattern": "string — polisher vs sprinter",
      "plotter_pantser": "string — where on the spectrum"
    },
    "notable_patterns": ["array of specific observations"],
    "comparable_authors": ["array with specific comparisons"]
  },
  "influences": {
    "rhythm_from": ["authors and what was absorbed"],
    "structure_from": ["authors and what was absorbed"],
    "tone_from": ["authors and what was absorbed"],
    "anti_influences": ["what they reject and why"]
  },
  "anti_slop": {
    "personal_banned_words": ["words this specific writer hates"],
    "personal_banned_patterns": ["patterns that would make their prose feel fake"],
    "cringe_triggers": ["things that would break immersion for this writer"],
    "genre_constraints": ["genre-specific rules derived from interview"]
  },
  "voice_instruction": "string — the compiled 500-2000 word system prompt",
  "voice_summary": "string — 2-3 sentence human-readable summary of their voice"
}
```

**Database Storage:**
```sql
INSERT INTO voice_profiles (user_id, profile_name, literary_dna, influences, anti_slop, voice_instruction)
VALUES ($1, $2, $3::jsonb, $4::jsonb, $5::jsonb, $6);
```

Also add a `voice_summary` TEXT column to the `voice_profiles` table (migration needed):
```sql
ALTER TABLE voice_profiles ADD COLUMN voice_summary TEXT;
```

---

## Prompts (Protected — /prompts/ directory)

### File: `/prompts/sample_analysis.py`

```python
SAMPLE_ANALYSIS_SYSTEM = """You are a literary analyst with deep expertise in computational stylistics. You analyze writing samples to identify the distinctive patterns that make each writer unique.

You will receive a writing sample. Analyze it and return a JSON object with these exact keys. Be SPECIFIC to this writer — avoid generic observations.

{
  "vocabulary_tier": "Describe their vocabulary level and register precisely",
  "avg_sentence_length": "Characterize their typical sentence length",
  "sentence_variety": "How much do their sentence lengths and structures vary?",
  "pacing_style": "How do they control the speed of reading?",
  "emotional_register": "How do they handle emotional content?",
  "sensory_preference": "Which senses dominate their prose?",
  "dialogue_style": "How do they write dialogue? Tags? Rhythm? Subtext?",
  "pov_tendency": "What point of view and narrative distance?",
  "tense_preference": "What tense(s) do they write in?",
  "dark_humor_quotient": "Is humor present? What kind?",
  "notable_patterns": ["3-5 SPECIFIC observations unique to THIS writer"],
  "comparable_authors": ["2-3 authors with SPECIFIC element comparisons — e.g., 'Dialogue rhythm reminiscent of Elmore Leonard's ear for vernacular'"]
}

Be generous but honest. This is a discovery moment for the writer — they should feel SEEN, not flattered. Find what's genuinely distinctive, not what's common. If their dialogue is their strongest asset, say so and say why. If their pacing is unusual, describe the specific pattern.

Return ONLY the JSON object. No preamble, no markdown fencing."""


SAMPLE_ANALYSIS_USER = """Analyze this writing sample:

---
{writing_sample}
---

Context provided by the writer: {sample_context}"""
```

### File: `/prompts/interview_conductor.py`

```python
INTERVIEW_SYSTEM = """You are the Voice Discovery interviewer for BUB Writer, an AI writing tool that learns to write in each user's unique voice. Your job is to conduct a warm, perceptive, 7-10 question interview that maps this writer's creative DNA.

You have already analyzed a sample of their writing. Here are the results:

<style_markers>
{style_markers_json}
</style_markers>

YOUR PERSONALITY:
- You are genuinely curious about this writer's creative process
- You are warm but not sycophantic — you notice things and name them specifically
- You reference their actual writing sample when relevant ("I noticed your dialogue carries weight without attribution tags — that's a specific choice")
- You follow interesting threads — if a writer says something surprising, explore it
- You never use generic prompts like "Tell me about your writing style"
- You speak like a fellow writer who reads widely, not like a therapist or a survey

YOUR APPROACH:
- Start by acknowledging what you found in their sample (1-2 specific observations)
- Ask ONE question at a time — never stack questions
- Keep your responses concise (2-4 sentences of observation/acknowledgment + 1 question)
- Adapt your questions based on their answers — don't follow a rigid script
- Reference their previous answers to show you're actually listening
- After 7-10 exchanges, wrap up naturally

DIAGNOSTIC AREAS TO COVER (not in this exact order — weave them in naturally):
1. Worldview: How they see the world (funny? tragic? absurd? beautiful?)
2. The Question: What they're always trying to answer in their writing
3. Sensory Mode: Where they start when bringing a scene to life
4. Process: How much they plan vs discover, what they do when stuck
5. Anti-Preferences: What prose makes them cringe, what advice they reject
6. Influences: Who shaped their writing, what they absorbed vs rejected
7. The Deep Cut: Something specific you noticed that deserves exploration

IMPORTANT RULES:
- NEVER list multiple questions at once
- NEVER use bullet points in your responses
- Keep each response under 150 words
- Reference the writing sample naturally, not mechanically
- When the interview is complete (7-10 exchanges covered the diagnostic areas), end your final response with the exact string [INTERVIEW_COMPLETE] on its own line. This is a system signal — it will be stripped before showing to the user.
- Your final response before the signal should feel like a natural close: "I have a really clear picture of your voice now. Let me put this all together for you." or similar.

This interview IS the product demo. If the writer feels genuinely understood, they'll subscribe. If it feels like a survey, they won't."""


INTERVIEW_START = """The writer has submitted a writing sample and is ready for the interview. Begin by making 1-2 specific observations about their sample, then ask your first question.

Remember: Be specific. Reference their actual writing. Ask ONE question."""
```

### File: `/prompts/profile_compiler.py`

```python
PROFILE_COMPILER_SYSTEM = """You are the Voice DNA compiler for BUB Writer. You take the complete data from a Voice Discovery session — the writing sample analysis and the full interview transcript — and compile it into two outputs:

1. A structured Voice DNA Profile (JSON)
2. A compiled voice_instruction — a system prompt (500-2000 words) that will be injected into an LLM to make it write prose in this specific writer's voice

The voice_instruction is the most important output. It must be precise enough that a different AI model, reading only this instruction and nothing else, could produce prose that this writer would recognize as sounding like them.

VOICE INSTRUCTION STRUCTURE (this specific order is intentional):
1. CONSTRAINTS FIRST — What this writer NEVER does. Anti-preferences, banned patterns, cringe triggers.
2. IDENTITY — Who this writer is at the core. Worldview, the question they're answering, emotional orientation.
3. RHYTHM & MECHANICS — Sentence length patterns, paragraph structure, pacing, tense, POV.
4. VOICE TEXTURE — Vocabulary register, dialogue style, humor approach, sensory preferences.
5. INFLUENCES — Not "write like X" but specific absorbed techniques: "Uses [author]'s technique of [specific thing]"
6. ANTI-SLOP — Specific words and patterns that would make output feel fake for this writer.

CRITICAL PRINCIPLES FOR THE VOICE INSTRUCTION:
- Use concrete, measurable descriptions: "Sentences average 12-16 words with occasional 3-5 word punches" not "Varies sentence length"
- Include negative constraints: "NEVER uses 'nodded knowingly'" not just "Avoids clichés"
- Reference specific techniques from the sample: "Dialogue without attribution tags when two characters are established"
- The instruction should feel like a detailed brief to a ghostwriter, not a personality quiz result
- Include 2-3 short example phrases or patterns from the writer's actual sample as style anchors

Return a JSON object with these exact keys:

{
  "literary_dna": {
    "vocabulary_tier": "string",
    "sentence_rhythm": "string — be specific about patterns",
    "pacing_style": "string",
    "emotional_register": "string",
    "sensory_mode": "string",
    "dialogue_approach": "string",
    "pov_preference": "string",
    "tense_preference": "string",
    "humor_style": "string",
    "darkness_calibration": "string",
    "cognitive_style": {
      "processing_mode": "visual/verbal/abstract/concrete",
      "story_entry_point": "character/world/conflict first",
      "revision_pattern": "polisher vs sprinter",
      "plotter_pantser": "spectrum position"
    },
    "notable_patterns": ["3-5 specific patterns"],
    "comparable_authors": ["2-3 specific comparisons"]
  },
  "influences": {
    "rhythm_from": ["specific absorbed rhythmic techniques from named authors"],
    "structure_from": ["specific absorbed structural techniques"],
    "tone_from": ["specific absorbed tonal qualities"],
    "anti_influences": ["what they actively reject and why"]
  },
  "anti_slop": {
    "personal_banned_words": ["words this writer would never use"],
    "personal_banned_patterns": ["structural patterns that would feel fake"],
    "cringe_triggers": ["things that would break immersion"],
    "genre_constraints": ["genre-specific rules"]
  },
  "voice_instruction": "THE COMPILED SYSTEM PROMPT — 500-2000 words, following the structure above",
  "voice_summary": "2-3 sentence human-readable summary of their voice"
}

Return ONLY the JSON object. No preamble, no markdown fencing."""


PROFILE_COMPILER_USER = """Compile the Voice DNA Profile from this session data:

WRITING SAMPLE ANALYSIS:
{style_markers_json}

INTERVIEW TRANSCRIPT:
{interview_transcript}

ORIGINAL WRITING SAMPLE (first 2000 words):
{writing_sample_truncated}"""
```

---

## Frontend Implementation

### Voice Discovery Page: `/src/app/(app)/voice/page.tsx`

**Replace the placeholder with a multi-step flow:**

**Step 1: Sample Submission**
- Large textarea: "Paste 500+ words of your writing"
- Smaller textarea below: "What is this from? (optional)" — context field
- Word counter that updates live (show "X / 500 minimum")
- Submit button: "Analyze My Writing" — disabled until 500+ words
- On submit: POST to `/api/voice-discovery/analyze`
- Show loading state: "Reading your work..." with subtle animation

**Step 2: Sample Results + Interview Start**
- Display the `style_markers` in a clean card layout — NOT a data dump
- Show each marker as a labeled insight, e.g.:
  - **Vocabulary** — "Literary-Accessible: You use precise words but never show off"
  - **Rhythm** — "Your sentences average 14 words with sharp 4-word punches for emphasis"
  - **Sensory World** — "Visual-dominant: You paint scenes before you animate them"
  - **Comparable Voices** — "Dialogue rhythm reminiscent of Elmore Leonard..."
- Below the results: "Ready to go deeper? The interview takes about 10 minutes."
- Button: "Start Interview" → transitions to Step 3

**Step 3: The Interview**
- Chat-like interface but NOT a chat bubble UI — more like a Q&A flow
- AI messages appear as clean prose paragraphs (left-aligned, no avatar, no bubble)
- User input is a text area at the bottom (not a chat input — larger, 3-4 lines visible)
- Submit button or Ctrl+Enter to send
- SSE streaming shows AI response appearing word by word
- Show a subtle progress indicator: "Question 3 of ~8" (approximate, since interview length varies)
- When `interview_complete` is true:
  - Show the final AI message
  - Transition to Step 4

**Step 4: Profile Generation**
- Input field: "Name this voice profile" with default "My Voice"
- Button: "Generate My Voice DNA"
- On click: POST to `/api/voice-discovery/finalize`
- Loading state: "Compiling your literary DNA..." (this call takes 10-20 seconds)
- When complete: Transition to Step 5

**Step 5: Profile Display**
- Show the complete profile in a beautiful, readable layout
- `voice_summary` as the hero text at the top
- Literary DNA as a card grid (same style as Step 2 but more detailed)
- Influences section
- Anti-Slop section (writers will LOVE seeing their banned word list)
- The `voice_instruction` in an expandable/collapsible section: "Your compiled voice instruction (this is what the AI uses to write like you)"
- CTA button: "Start Writing" → navigates to create a new project with this voice profile

### UI Design Notes
- Maintain the existing dark aesthetic from the landing page
- Use the Geist font family already in the project
- Animations should be subtle — fade-ins, not bounces
- The interview step should feel like a conversation, not a form
- No borders on cards — use subtle background color differences (e.g., zinc-900 cards on zinc-950 background)
- Text should be warm white (zinc-100) with zinc-400 for secondary text
- Accent color: one warm highlight color for interactive elements (keep consistent with landing page buttons)

---

## LLM Service Updates

**File:** `app/services/llm_service.py`

Update the LLM service to support:

1. **Non-streaming calls** (for analyze and finalize):
```python
async def generate(
    self,
    system_prompt: str,
    user_prompt: str,
    model: str = "deepseek-ai/DeepSeek-V3",
    temperature: float = 0.7,
    max_tokens: int = 4000,
    response_format: dict | None = None  # for JSON mode if supported
) -> str:
```

2. **Streaming calls** (for interview):
```python
async def generate_stream(
    self,
    system_prompt: str,
    messages: list[dict],  # full conversation history
    model: str = "deepseek-ai/DeepSeek-V3",
    temperature: float = 0.8,
) -> AsyncIterator[str]:
```

**Provider:** DeepInfra (primary), Fireworks (fallback) — same pattern as BUB AI.
**Model:** `deepseek-ai/DeepSeek-V3` for all three calls.
**Temperature:** 0.7 for analysis, 0.8 for interview (slightly more creative), 0.7 for compilation.

Use the OpenAI-compatible API format that DeepInfra supports:
```python
import openai

client = openai.AsyncOpenAI(
    api_key=settings.deepinfra_api_key,
    base_url="https://api.deepinfra.com/v1/openai"
)
```

---

## API Endpoint for Voice Profile Listing

**Endpoint:** `GET /api/voice-profiles`
**Auth:** Required (JWT)
**Response:**
```json
{
  "profiles": [
    {
      "id": "uuid",
      "profile_name": "string",
      "voice_summary": "string",
      "created_at": "datetime",
      "updated_at": "datetime"
    }
  ]
}
```

Query: `SELECT id, profile_name, voice_summary, created_at, updated_at FROM voice_profiles WHERE user_id = $1 ORDER BY updated_at DESC`

---

## Database Migration

Run this in Supabase SQL Editor after the phase is built:

```sql
-- Add voice_summary column
ALTER TABLE voice_profiles ADD COLUMN IF NOT EXISTS voice_summary TEXT;
```

---

## Error Handling

- If the LLM returns invalid JSON from analyze or finalize, retry once. If still invalid, return 500 with: "Analysis failed — please try again."
- If the session expires mid-interview, return 410 Gone with: "Your session expired. Please start a new voice discovery."
- If DeepInfra is down, fall back to Fireworks automatically (same model path).
- Wrap all LLM calls in try/except with specific error logging.

---

## What NOT to Touch

- `/prompts/` directory contents are protected IP — Claude Code creates the files but Jayson reviews before merge
- `billing_service.py` — no changes
- `voice_profiles` table schema (existing columns) — only ADD the `voice_summary` column
- Stripe webhook handler — no changes
- Anti-Slop word lists — will be added in Phase 3, not here

---

## Acceptance Criteria

1. **Analyze endpoint works:** POST a 500+ word writing sample → receive structured style_markers JSON
2. **Interview streams:** SSE streaming produces word-by-word AI responses that adapt to user answers
3. **Interview feels human:** The AI references the writing sample, follows interesting threads, doesn't feel scripted
4. **Profile compiles:** After interview completion, finalize produces a complete Voice DNA Profile with a voice_instruction
5. **Profile stores:** Profile is saved to Supabase and appears in the profiles list endpoint
6. **Frontend flow works:** User can go from paste → analysis → interview → profile in a single session
7. **Session management:** Sessions expire after 2 hours, expired sessions return appropriate errors
8. **Error resilience:** LLM failures are handled gracefully with retry and user-friendly messages

---

## Testing Script (Jayson — manual)

1. Sign in via Google OAuth
2. Paste 500+ words of Kickdown prose into the sample textarea
3. Verify analysis results feel accurate and specific to Kickdown's voice
4. Go through the full interview — answer honestly
5. Verify the AI references your actual writing sample during the interview
6. Verify the AI asks follow-up questions based on your answers (not scripted)
7. Generate the profile
8. Read the `voice_instruction` — does it capture your voice accurately enough that you'd trust it to write a Kickdown scene?
9. Check the profile appears in the profiles list
10. Test error cases: submit < 500 words (should reject), try to finalize without completing interview (should reject)
