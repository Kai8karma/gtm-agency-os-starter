# BRAND GUIDELINES — GTM Agency OS Starter

> Pattern 3: brand lives in the repo. Updates go through PR review, not a Notion deck no one opens.

This file is the default voice card for the starter template. Per-engagement forks override it with the client's brand.

---

## Voice attributes

| Attribute | Default | Override path |
|---|---|---|
| Reading level | 9th grade | `clients/<slug>/client.md` |
| Sentence length | 8–14 words median | per-client override |
| Hedge density | < 1 hedge per 100 words | strict, do not soften |
| Emoji policy | None in committed files. Sparing in Slack (✓ ✗ ⚠ only). | per-client override |
| Voice axis | Direct, decision-first, brain-native | non-overridable |

---

## Banned phrases (instant rejection in PR review)

These trigger the eval voice-match check. Score < 8.0 if any appear in agent output.

- "world-class"
- "cutting-edge"
- "game-changing"
- "revolutionary"
- "innovative" (when used as filler)
- "really", "very", "quite", "actually" (hedge adverbs)
- "unleash", "elevate", "supercharge" (marketing verbs)
- "synergy", "leverage" (when used as a noun)
- "in today's fast-paced world" and any variant
- "we're excited to announce"
- "thrilled to share"

---

## Required affordances

Every agent output must:

1. **Lead with the verdict.** First sentence states the decision or the headline finding.
2. **Cite sources by ID.** Memory IDs, file paths, or run IDs — not vague "based on what I found."
3. **End with provenance.** One line: agent name + timestamp + eval pass/fail (if applicable).
4. **Use sentence-case headers.** "Weekly review" not "Weekly Review" or "WEEKLY REVIEW."
5. **Prefer numbers over adjectives.** "47 leads, 12 replies, 4 booked" beats "strong response rates."

---

## Slack-specific rules

- DMs > channel posts when the message is owner-specific (Pattern 13).
- One slash command per major action. No `/do-everything`.
- Status emoji limited to ✓ (done), ✗ (failed), ⚠ (needs review), ⏳ (in progress).
- Threads are mandatory for any reply > 200 characters.

---

## Client-facing copy (outbound campaigns)

Outbound copy goes through `agents/campaign-drafter.md`. Required guardrails:

- Subject line: ≤ 6 words, no clickbait formulas ("you won't believe…", "the secret to…").
- Body: ≤ 90 words for cold first-touch.
- One CTA. Never two.
- Personalization token must reference verifiable surface signal (LinkedIn post date, hiring page change, funding announcement). No generic "I noticed your company is doing well."
- Sender persona stays consistent within a sequence.

---

## Brand-as-code workflow

1. Edits to this file land via PR.
2. The PR runs `make eval` — voice-match fixtures cite this file.
3. Below-threshold runs block merge.
4. Quarterly: prune banned-phrases list. Patterns 9.

---

**Provenance:** kai8karma, 2026-05-09. This is the template default. Each forked engagement replaces this file with the client's brand card.
