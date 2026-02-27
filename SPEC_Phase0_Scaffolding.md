\# SPEC: Phase 0 — Project Scaffolding



\## Objective

Set up the complete project structure for BUB Writer with a working FastAPI backend and Next.js frontend that can communicate. No features yet — just the skeleton that everything else builds on.



\## What to Build



\### Backend (FastAPI)



Create a FastAPI application with the following structure:



```

backend/

├── app/

│   ├── \_\_init\_\_.py

│   ├── main.py                 # FastAPI app, CORS, lifespan

│   ├── config.py               # Pydantic Settings (env vars)

│   ├── auth/

│   │   ├── \_\_init\_\_.py

│   │   └── dependencies.py     # Supabase JWT verification (ES256)

│   ├── routers/

│   │   ├── \_\_init\_\_.py

│   │   ├── health.py           # GET /api/health

│   │   ├── voice\_discovery.py  # Placeholder router

│   │   ├── projects.py         # Placeholder router

│   │   ├── generation.py       # Placeholder router

│   │   ├── billing.py          # Placeholder router

│   │   └── analyze\_free.py     # Placeholder router (public, no auth)

│   ├── services/

│   │   ├── \_\_init\_\_.py

│   │   ├── supabase\_client.py  # Supabase client initialization

│   │   ├── llm\_service.py      # Placeholder for DeepSeek/Claude calls

│   │   └── billing\_service.py  # Placeholder for Stripe

│   ├── models/

│   │   ├── \_\_init\_\_.py

│   │   └── schemas.py          # Pydantic request/response models

│   └── prompts/                # System prompt templates (PROTECTED)

│       └── .gitkeep

├── requirements.txt

├── Procfile                    # For Railway: web: uvicorn app.main:app --host 0.0.0.0 --port $PORT

├── railway.toml                # Railway config

└── .env.example

```



\#### main.py Requirements:

\- FastAPI app with title "BUB Writer API"

\- CORS middleware configured from ALLOWED\_ORIGINS env var

\- Include all routers with /api prefix

\- Health check endpoint at /api/health returning { "status": "ok", "service": "bub-writer" }



\#### config.py Requirements:

\- Use Pydantic Settings with env vars

\- Include flexible validators for list fields (ALLOWED\_ORIGINS can be comma-separated string or list)

\- All env vars from CLAUDE.md's Railway section



\#### auth/dependencies.py Requirements:

\- ES256 JWT verification function (manual decoder pattern, NOT python-jose)

\- Returns user\_id from token

\- Raises 401 on invalid/expired tokens

\- Use as FastAPI Depends() on protected routes



\#### Placeholder Routers:

Each placeholder router should have a single endpoint that returns { "status": "not\_implemented", "router": "<name>" } so we can verify routing works.



\### Frontend (Next.js)



Create a Next.js 14 App Router application:



```

frontend/

├── src/

│   ├── app/

│   │   ├── layout.tsx          # Root layout with metadata, fonts

│   │   ├── page.tsx            # Landing page (placeholder)

│   │   ├── globals.css         # Tailwind base styles + dark mode

│   │   ├── (auth)/

│   │   │   ├── login/

│   │   │   │   └── page.tsx    # Login page (placeholder)

│   │   │   └── callback/

│   │   │       └── page.tsx    # Supabase auth callback

│   │   ├── (app)/

│   │   │   ├── layout.tsx      # App layout (sidebar, nav — placeholder)

│   │   │   ├── dashboard/

│   │   │   │   └── page.tsx    # Dashboard (placeholder)

│   │   │   ├── project/

│   │   │   │   └── \[id]/

│   │   │   │       └── page.tsx # Writing workspace (placeholder)

│   │   │   └── voice/

│   │   │       └── page.tsx    # Voice Discovery (placeholder)

│   │   └── analyze/

│   │       └── page.tsx        # DNA Analyzer (public, no auth)

│   ├── lib/

│   │   ├── supabase/

│   │   │   ├── client.ts       # Browser Supabase client

│   │   │   └── server.ts       # Server Supabase client

│   │   ├── api.ts              # Fetch wrapper for backend API calls

│   │   └── utils.ts            # Shared utilities

│   ├── components/

│   │   └── ui/                 # Shared UI components (empty for now)

│   └── types/

│       └── index.ts            # TypeScript type definitions

├── public/

├── tailwind.config.ts

├── tsconfig.json

├── next.config.js

├── package.json

└── .env.example

```



\#### Key Frontend Requirements:

\- Tailwind CSS configured with dark mode (class strategy)

\- Supabase Auth configured for Google SSO

\- Auth callback handler at /callback

\- Protected routes under (app)/ check for authenticated session

\- API wrapper in lib/api.ts that:

&nbsp; - Attaches Supabase JWT to Authorization header

&nbsp; - Handles errors consistently

&nbsp; - Supports SSE streaming for generation endpoints

\- All placeholder pages show the page name and "Coming Soon" with consistent styling



\### Database (Supabase SQL)



Create a migration file with:



```sql

-- Voice DNA profiles

CREATE TABLE voice\_profiles (

&nbsp; id UUID PRIMARY KEY DEFAULT gen\_random\_uuid(),

&nbsp; user\_id UUID NOT NULL REFERENCES auth.users(id),

&nbsp; profile\_name TEXT NOT NULL,

&nbsp; literary\_dna JSONB NOT NULL,

&nbsp; influences JSONB DEFAULT '{}',

&nbsp; anti\_slop JSONB DEFAULT '{}',

&nbsp; voice\_instruction TEXT,

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

&nbsp; brain\_output TEXT,

&nbsp; voice\_output TEXT NOT NULL,

&nbsp; polish\_output TEXT,

&nbsp; word\_count INTEGER,

&nbsp; created\_at TIMESTAMPTZ DEFAULT now()

);



-- User subscriptions

CREATE TABLE subscriptions (

&nbsp; id UUID PRIMARY KEY DEFAULT gen\_random\_uuid(),

&nbsp; user\_id UUID NOT NULL REFERENCES auth.users(id),

&nbsp; stripe\_customer\_id TEXT,

&nbsp; stripe\_subscription\_id TEXT,

&nbsp; tier TEXT NOT NULL DEFAULT 'free',

&nbsp; status TEXT NOT NULL DEFAULT 'active',

&nbsp; current\_period\_end TIMESTAMPTZ,

&nbsp; created\_at TIMESTAMPTZ DEFAULT now(),

&nbsp; updated\_at TIMESTAMPTZ DEFAULT now()

);



-- RLS Policies

ALTER TABLE voice\_profiles ENABLE ROW LEVEL SECURITY;

ALTER TABLE projects ENABLE ROW LEVEL SECURITY;

ALTER TABLE generations ENABLE ROW LEVEL SECURITY;

ALTER TABLE subscriptions ENABLE ROW LEVEL SECURITY;



-- voice\_profiles policies

CREATE POLICY "Users can view own voice profiles"

&nbsp; ON voice\_profiles FOR SELECT

&nbsp; USING (auth.uid() = user\_id);



CREATE POLICY "Users can create own voice profiles"

&nbsp; ON voice\_profiles FOR INSERT

&nbsp; WITH CHECK (auth.uid() = user\_id);



CREATE POLICY "Users can update own voice profiles"

&nbsp; ON voice\_profiles FOR UPDATE

&nbsp; USING (auth.uid() = user\_id);



CREATE POLICY "Users can delete own voice profiles"

&nbsp; ON voice\_profiles FOR DELETE

&nbsp; USING (auth.uid() = user\_id);



-- projects policies

CREATE POLICY "Users can view own projects"

&nbsp; ON projects FOR SELECT

&nbsp; USING (auth.uid() = user\_id);



CREATE POLICY "Users can create own projects"

&nbsp; ON projects FOR INSERT

&nbsp; WITH CHECK (auth.uid() = user\_id);



CREATE POLICY "Users can update own projects"

&nbsp; ON projects FOR UPDATE

&nbsp; USING (auth.uid() = user\_id);



CREATE POLICY "Users can delete own projects"

&nbsp; ON projects FOR DELETE

&nbsp; USING (auth.uid() = user\_id);



-- generations policies (access through project ownership)

CREATE POLICY "Users can view own generations"

&nbsp; ON generations FOR SELECT

&nbsp; USING (

&nbsp;   EXISTS (

&nbsp;     SELECT 1 FROM projects

&nbsp;     WHERE projects.id = generations.project\_id

&nbsp;     AND projects.user\_id = auth.uid()

&nbsp;   )

&nbsp; );



CREATE POLICY "Users can create generations in own projects"

&nbsp; ON generations FOR INSERT

&nbsp; WITH CHECK (

&nbsp;   EXISTS (

&nbsp;     SELECT 1 FROM projects

&nbsp;     WHERE projects.id = generations.project\_id

&nbsp;     AND projects.user\_id = auth.uid()

&nbsp;   )

&nbsp; );



-- subscriptions policies

CREATE POLICY "Users can view own subscription"

&nbsp; ON subscriptions FOR SELECT

&nbsp; USING (auth.uid() = user\_id);

```



\## What NOT to Touch

\- Do not create any actual prompt templates yet (just the /prompts/ directory)

\- Do not implement any LLM calls yet (just the service placeholder)

\- Do not implement Stripe checkout yet (just the billing router placeholder)

\- Do not build the writing editor UI yet (just the placeholder page)



\## Acceptance Criteria

1\. Backend starts with `uvicorn app.main:app` and responds to GET /api/health

2\. All placeholder routers respond at their expected paths

3\. CORS allows requests from the frontend URL

4\. JWT auth dependency correctly validates Supabase ES256 tokens

5\. Frontend builds with `npm run build` and displays placeholder pages

6\. Supabase auth login flow works (redirect to Google → callback → session)

7\. Protected frontend routes redirect to login when no session exists

8\. Frontend can call backend /api/health and display the response

9\. Database migration runs clean in Supabase SQL editor

10\. RLS policies prevent cross-user data access



\## Terminal Environment

Jayson uses PowerShell. All commands should be PowerShell-compatible.

