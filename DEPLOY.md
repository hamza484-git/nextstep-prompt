# Deploy `nextstep-prompt` to Vercel

One deployment serves **both the Inspector dashboard and the API** from the same URL:

| Path                         | What it serves                                          |
|------------------------------|---------------------------------------------------------|
| `/`                          | Inspector dashboard (static)                            |
| `/api/health`                | JSON — provider, model, prompt version                  |
| `/api/prompt`                | JSON — the exact system prompt + schema hint            |
| `/api/reason` (POST)         | JSON — full ReasoningResult for arbitrary input         |
| `/api/eval-report?kind=mock` | markdown — `evals/report.md`                            |
| `/api/eval-report?kind=gemini` | markdown — `evals/report_gemini.md`                   |

So a reviewer can **use the dashboard** by opening the URL, or **test the reasoning layer directly** with curl.

---

## One-time setup

```bash
npm i -g vercel
cd C:\Users\hamza\OneDrive\Desktop\Hazhteq\nextstep-prompt
vercel login
```

---

## Deploy

```bash
vercel --prod
```

Answer the prompts:
1. **Set up and deploy?** → `y`
2. **Link to existing project?** → `n`
3. **Project name?** → `nextstep-prompt-<yourname>`
4. **Directory?** → `.`
5. **Override settings?** → `n`

After ~60 seconds you get a production URL.

---

## Set the Gemini API key

Without a key, the deployed inspector uses the deterministic MockProvider — 30/30 on the fixture set, but it can't reason about arbitrary input.

**CLI:**
```bash
vercel env add GEMINI_API_KEY production
vercel --prod
```

**Or via dashboard:** vercel.com → project → Settings → Environment Variables → add `GEMINI_API_KEY` scoped to Production, then Redeploy.

---

## Verify

```bash
# should show provider: gemini
curl https://your-deployment.vercel.app/api/health

# reason about arbitrary input
curl -X POST https://your-deployment.vercel.app/api/reason \
  -H "Content-Type: application/json" \
  -d "{\"text\":\"kal submission hai laptop dead ho gaya\"}"

# open the dashboard
start https://your-deployment.vercel.app/
```

---

## Serverless caveats

- **Reasoning layer is stateless** — no session store, no ledger. Every request stands alone. Perfect fit for serverless.
- **Cold start ~1–2s.**
- **Eval reports** (`evals/report.md`, `evals/report_gemini.md`) are shipped as static files in the deployment. To regenerate:
  ```bash
  # locally
  python evals/runner.py --provider gemini --out evals/report_gemini.md
  git commit -am "refresh gemini eval report"
  vercel --prod
  ```

---

## Redeploying after code changes

```bash
git commit -am "…"
vercel --prod
```
