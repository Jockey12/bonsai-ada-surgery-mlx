# Bonsai quality research: report (2026-09-29 to 2026-10-04)

All runs on one RTX 4070 12 GB, unattended, paired arms with plans and gates frozen before results (`bench/*-plan.json`).
Everything here is from the pinned serve configuration A (same binaries, model and template throughout) unless stated.

## Bottom line

1. **No serving change is promoted.** The best lead, a larger reasoning budget, did not survive replication.
   The 20480-token budget (server default and the Mac harness's
   per-request value) force-closes thinking mid-sentence on hard problems, and the model
   then guesses. On 16 frozen, paired hard problems, budget 40960 answered **13/16 vs 8/16** correctly:
   **5 wrong->correct, 0 correct->wrong** (one-sided sign test p = 0.031). **Replication on fresh seeds of
   the same families: 4/8 vs 4/8, 0 rescues, 0 losses (gate not met).** Transfer to a new, harder family (LCS counting) did **not** pass its gate (1 rescue, 0
   losses, 5 wrong in both arms: floor effect). Cost: ~1.9x tokens and wall time, only on problems that hit
   the cap. Across all 32 pairs (descriptive, not a declared test): 6 rescues, 0 losses. So: a larger budget
   never hurt, sometimes helped, and the size of the benefit is unknown and likely smaller than the first
   run suggested (those families were chosen because they overflow the budget).
2. **Consistent with (not proof about) the failures in the A baseline.** The only two A responses (of 58) whose thinking was
   force-closed by the budget are the first turns of the only two functionally failed tasks (both bundle
   seeds), cut off mid-word ("...CRC + ISIZE in theNow produce the complete answer."). Not proven causal for
   those tasks (their code cannot be executed here), but it is the same mechanism.
3. **H1 (empty-think history) rejected as a thinking-suppression mechanism.** The template renders every past
   assistant turn as `<think>{reasoning_content}</think>`, and clients drop reasoning_content, so tool loops
   show the model empty think blocks. Replaying 6 real A repair points with the reasoning restored did not
   change how much the model thinks (5 longer / 7 shorter, p = 0.81). A server-side `--reasoning-cache`
   (restores it transparently) is built, functionally verified and parked on a branch, with no quality claim.
4. **Not serving defects** (checked, cleared): tokenizer round trip of U+2028/U+0085/tabs/trailing spaces;
   XML tool-argument parser (verbatim string values; the only trimming helper is dead code); `--backend-sampling`
   (inert for every thinking request: disabled whenever a reasoning budget or grammar is active).

## What to change (recommendations, not yet applied to the live server)

- Clients / the Mac harness (optional, per request, no server change): for hard single-shot work where
  latency is acceptable, `reasoning_budget_tokens: 40960` with `max_tokens >= 45056`. Never observed to hurt.
- Server default: unchanged (20480). Branch `quality/think-budget` in the serve repo (NOT merged) only fixes
  the launcher so a larger `BONSAI_THINK_BUDGET` does not cut requests that omit max_tokens
  (`-n = max(24576, budget + 4096)`, a no-op today). Whether to run with 40960 is a latency-vs-maybe-accuracy
  call for you, not something the evidence settles.
- Worth trying next: a gentler forced closure (finish the current line, then "\n\n" + message) for the cases
  that still hit the cap; the current closure splices the message mid-word.

## Experiments (all frozen before treatment results; plans in `bench/*-plan.json`)

| Experiment | Tasks | Result |
| --- | --- | --- |
| Pilots: host-simulated tool tasks (invoice, dedupe, ledger, chain, copy, 3-4x larger variants) + regex debug loops | 23 attempts, arm P0 | 21/23 full pass (ceiling). Only fails: exact byte copy 0/2, genuine model copy errors |
| H2 budget 20480 vs 40960 | knapsack + digits, seeds 11-18 | 8/16 vs 13/16; 5 rescues, 0 losses, p = 0.031 |
| H2 transfer | lcs seeds 21-26 (+ grid 23, 25 no-trip control) | lcs 0/6 vs 1/6: gate not met (floor); grid unchanged, both correct |
| H2 replication | knapsack + digits, fresh seeds 31-34 | 4/8 vs 4/8, 0 rescues, 0 losses: gate not met |
| H1 replay (mechanism) | 6 real A repair points x 2 reps | no thinking-length effect (p = 0.81) |
| --reasoning-cache functional | live server, temporary | restored = true, no leak to foreign ids |

## State at hand-back

- Live server: pinned A (`switch.ps1 -Arm A`), from `bin\` (unchanged bytes), speculative on, slot idle.
- Tunnel: DOWN (was already gone at takeover with every server window; the old URL is dead). Not restarted
  unattended because it opens a new public endpoint. To restore: `bin\cloudflared.exe tunnel --url
  http://localhost:8080` (new trycloudflare URL; tell the Mac).
- Serve repo: branch `quality/think-budget` (1 commit), main untouched. Fork: local branch
  `reasoning-cache` (3 commits on c8b8993), not pushed. `bin-rc770906f\` holds the cache build (not live).
- Provenance: this build tree stamps build-info only at CMake configure time, so `b10768-8ecc788d5` on every
  binary built since then says nothing about dirtiness; module byte-identity is the real evidence.
- Nothing was executed from model output. No downloads. No pushes.

## Round 2 (2026-09-29 daytime, full-auto)

| Experiment | Result |
| --- | --- |
| Arithmetic-slip census (68 traces) | Written arithmetic is essentially error-free; flagged "slips" were notation. Verified-arithmetic decoding not built |
| H3 temperature 0.6 vs 1.0 (budget 40960) | 9/12 vs 10/12, 0 rescues, 1 loss: rejected. 0.6 only finishes faster |
| H4 KV q8_0 exact recall (3-21k tokens) | 720/720: q8_0 cleared at these depths (f16 arm skipped, ceiling) |
| H5 vote of 3 x 12k budget vs 1 x 40k | 6/12 vs 9/12, 0 rescues, 3 losses, more tokens: rejected. Short samples are rarely right, so voting cannot help |
| H6 budget 81920 vs 40960 (digits) | 6/6 vs 5/6, 1 rescue, 0 losses: gate not met (ceiling) |

Across every budget comparison: larger budget 7 rescues, 0 losses in 44 pairs (descriptive only). The
consistent finding is that on long computations accuracy is limited by reasoning length, not by sampling
noise, arithmetic or the KV cache; misses at 40k are usually near-misses. No gated result supports changing the
server default; per-request budgets of 40960+ for hard single-shot work never hurt in any pair.

State at 16:35: llama-server stopped (GPU freed). Restart pinned A with
`artifacts\experiments\spec-ab-20260928\switch.ps1 -Arm A` (or start-server.ps1 for the product default).

## Round 3 (2026-09-29 evening)

| Experiment | Result |
| --- | --- |
| H7 soft landing (finish line + nudge + 4k grace) vs hard close at 20480 / 24576 | 7/12 vs 8/12 vs 8/12; 1 loss: rejected. After the nudge the model concludes at once, so the grace is unused; 20480 vs 24576 identical on all 12 |
| H8 budget notice in the system prompt, hard close 20480 | 4/12 vs 6/12; 1 rescue, 3 losses: rejected. Forced 12/12 in both arms: the model ignores a stated budget |

## Where this leaves us

Every single-shot serving or prompt lever tested is either neutral or harmful, except one: giving the model
substantially more thinking (40k+ tokens) on long computations. It never lost a pair (7 rescues / 0 losses in 44)
but never cleared a pre-declared gate on its own, so it is a per-request option, not a new default.
Cleared as causes: tokenizer, tool-argument parser, sampler path, temperature, q8_0 KV (to ~21k), arithmetic,
closure wording, history rendering. The remaining quality gap is the model's own long-horizon bookkeeping.
The untested frontier is agentic multi-turn work (the original AppWorld gap), which needs a real execution
sandbox on this PC (WSL/Docker/WASM) before it can be measured honestly.

## Round 4 (2026-09-30): sandbox, code tool, teacher reference, real agentic tasks

Setup: CPython 3.12 on WASI under wasmtime (tooling/wasi-python/sandbox.py), 12/12
isolation canaries pass (no host files, network or processes; memory and time capped). Teacher Qwen3.8-27B
UD-Q4_K_M downloaded and verified (sha256 322e194f...). Model-written code runs only inside that sandbox.

| Experiment | Result |
| --- | --- |
| E1 code tool (run_python) vs thinking only, knapsack+digits | 10/12 vs 5/12, 5 rescues, 0 losses (p=0.031); 8x fewer tokens, 7x faster. PASS |
| E1 transfer, lcs+subsets (new families) | 11/12 vs 6/12, 5 rescues, 0 losses (p=0.031); lcs 0/6 -> 5/6. PASS |
| C1 teacher vs Bonsai, same prompt tokens, budget 20480 | 6/8 vs 5/8; median tokens equal (declared efficiency test not met). Knapsack: teacher 4/4 in 4-9k tokens vs Bonsai capped; digits: identical |
| E2 budget 40960 vs 20480 on the A baseline's real coding cases (oracle-graded) | functional 4/9 vs 3/9, 1 rescue: gate not met. Bundle 1/12 overall; every bundle attempt hit the 12-response cap |
| H10 public-example checker tool on bundle | 0/6 vs 0/6: rejected; the model called it 0-1 times |
| E3 interpreter proxy no-harm (no client tools) | 18/18 vs 17/18, 0 losses, fewer tokens and time, no leaks. PASS |
| E4 interpreter proxy with client tools | 10/15 vs 11/15, 2 losses: FAIL -> default policy changed (interpreter only without client tools) |

What this means:
- The first supported quality gain: let the model compute with code. It moves long bookkeeping, Bonsai's weak
  spot, out of its reasoning. tooling/interpreter_proxy.py delivers it to any OpenAI-style client on :8081.
  Default policy (from E4): on for requests without client tools, passthrough for requests with their own tools,
  per-request override "code_interpreter": true/false. Not deployed; serving through :8081 left as a product decision.
- Compression is partly to blame, problem-dependent: on some problems the full-precision teacher needs a fraction
  of the thinking; on long DP both hit the same wall.
- Real agentic coding (bundle) stays hard for this model under a 12-response cap: neither more thinking nor a
  grader-backed checker moved it. The model under-uses offered feedback tools.
- Ops: issue #1 fixed (PR #2, release bundle-20260930).

## Round 5 (night of 2026-09-30 to 2026-10-01)

| Experiment | Result |
| --- | --- |
| E5 interpreter proxy on CSV data questions | 12/12 vs 8/12, 4 rescues, 0 losses: PASS (third gated pass for code) |
| E6 bundle with 24 vs 12 responses | 0/6 vs 1/6: rejected, not turn-limited |
| E7 interpreter proxy on access-log questions | 11/12 vs 10/12, 2 rescues, 1 loss: gate not met (round cap ended without an answer; slower on this family) |
| E8 bundle + verified tarfile/gzip notes in the prompt | 6/6 vs 0/6, p = 0.016: PASS |
| E8R same on a different hidden case, fresh seeds | 5/6 vs 0/6, p = 0.031: PASS (replicated), also ~35% fewer tokens |

Headline: Bonsai's real-coding failures were an API-knowledge gap. More thinking, more turns and a grader-backed
checker all failed; one page of accurate library facts took the task from 0/12 to 11/12. The general lever is
documentation retrieval for coding: give the model the exact APIs it needs. Second lever (3 gated passes, 1 miss):
computation through the sandboxed interpreter proxy for plain data questions. Open item: proxy final round must
always produce an answer.

## Round 6 (2026-10-01 daytime): building the gains into the server

Goal: users should get the gains without assembling anything. Built an integrated server-side layer (API cards,
API check, sandboxed Python tool) and started a raw-vs-layer product benchmark (P1).

| Step | Result |
| --- | --- |
| Sandbox working directory | Harness defect found and fixed: model test scripts could not open workspace files by relative path. Present in both arms of all earlier coding runs (comparisons stay paired). Canaries 14/14 |
| API linter | 0 warnings on 19 functionally correct solutions; flags invented names (10 of 30 baseline bundle attempts contain one). A false positive on local imports (`import solution`) was found and fixed; it voided a partial P1 run |
| Auto-generated API cards v1 / v2 vs hand-written notes (E9) | functional 1/6, 2/6 vs 5/6: neither card design adopted. With notes the model uses `tarfile`; with cards it still hand-rolls the format |
| Hand-written notes, cumulative (E8, E8R, E9) | 16/18 functional vs ~1/30 without help |
| E9b: same v2 cards at the END of the user message, without / with one generic "use the library" sentence | 4/6 and **6/6** vs notes 6/6: the automatic version with the sentence is adopted (placement was the main factor) |
| P1 product benchmark | paused until the card design is settled; partial runs kept, not scored |

Status: the docs lever is now automatic: cards introspected from the runtime, appended to the end of the first user message with one task-independent sentence, matched hand-written notes (6/6) on the bundle task. Transfer to other libraries is untested. The product benchmark (P1d) runs with this design. The interpreter
lever stands as before (3 gated passes, off by default for requests that bring their own tools).
Deliverables this round: a failure report with traces for PrismML (private), `layer/` snapshot (proxy with cards,
linter, interpreter, streaming passthrough), launcher integration on a local branch (not merged).

## Round 7 (2026-10-01 evening): product benchmark of the integrated layer (P1d, P1e)

Same frozen plan, every request sent once to the raw server and once through the layer. 74/74 runs, no infra errors.

| Set | Raw | Layer | Rescues / losses |
| --- | ---: | ---: | --- |
| GAIN (bundle, knapsack, digits, sales, weblog) | 10/20 | 16/20 | 6 / 0 (p = 0.016), gate pass |
| REGRESSION (checklist, batch, workspace) | 12/17 | 14/17 | 3 / 1, gate pass as declared |

Read with two caveats. The two bundle cases are the same four trajectories graded twice, so independent gain
rescues are 4 (bundle 2, digits 1, sales 1), still 0 losses. The batch rescues were an artifact: the layer wrongly
injected API cards into a non-coding task (any code fence counted as "coding") and the model then called the batch
tool 2 to 10 times. Detection now requires a coding tool, a python fence or an import line; a recheck (P1e, 4
pairs) shows the layer passing batch requests through unchanged (same tokens, same verdicts, 1/4 both arms).

| Family | Raw | Layer | Note |
| --- | ---: | ---: | --- |
| knapsack | 3/3 | 3/3 | 16.9k -> 1.9k tokens |
| digits | 2/3 | 3/3 | |
| sales table | 2/3 | 3/3 | |
| weblog | 3/3 | 3/3 | layer slower: 23k vs 10k tokens |
| bundle (trajectories) | 0/4 | 2/4 | below the 6/6 seen in the harness (E9b); failures use tarfile but have logic errors |
| checklist, workspace | same | same | |

Status: the computation lever holds inside the product with no losses. The coding lever is positive but weaker
than in the harness, on 4 trajectories. Open: whether the API-check notes on tool results hurt the bundle task,
weblog token cost, card transfer to other libraries.

Follow-up E10 (6 fresh bundle seeds): layer 4/6, layer with the API check off 3/6, harness card arm 5/6. The API
check does not hurt and stays on; the layer is within 1 of the harness. Bundle with automatic cards to date:
harness 11/12, layer 6/10, no help ~1/30. Decision: ship the layer as built.

## Round 8 (2026-10-02 night): transfer and product follow-ups

| Experiment | Result |
| --- | --- |
| E11 card transfer, ZIP archive task (`zipfile`) | raw 0/6, layer **5/6**, 0 losses: gate met |
| E11 card transfer, MIME email task (`email.message`) | raw 0/6, layer 0/6: no transfer; the model's solutions reject even the public example, and the email card lists `add_attachment` without its parameters |

Automatic API cards now help on two of three library families tried. | E12 input.txt: the user's message available to the Python tool as a file | correct 24/24 both arms; tokens on data questions **-58%** (weblog 176k -> 70k, sales 65k -> 31k over 6 seeds each); programs shrank from ~16k to ~1k characters when the model read the file instead of retyping the log. Adopted as default. Open: two digits seeds cost more |

| E13 streaming parity: same requests with `stream: true` through the layer's streaming tool loop | 12/12 vs 12/12, no tool-call deltas leaked, run notes visible in the reasoning stream. The Python tool now works for streaming clients |

| E14 repair note: one fixed sentence on failing tool results asking the model to reason about the cause first | bundle 3/6 vs 3/6, ZIP 3/6 vs 4/6: 2 rescues, 1 loss, gate not met; repair turns did not get deeper (median 769 vs 630 chars). Not adopted |

| E15 finish note: one fixed sentence asking the model to run its program on the task's example before answering | ZIP 4/6 vs **6/6**, email 0/6 vs 0/6: 2 rescues, 0 losses, gate met at its minimum. Adopted (weakly). On the email task the failures moved from "rejects the example" to content errors |


## Round 9 (2026-10-02): the shipped layer, measured (P2)

Fresh seeds, 74 runs, every request sent once to the raw server and once through the layer as it ships.

| Set | Raw | Layer | Rescues / losses |
| --- | ---: | ---: | --- |
| GAIN (bundle, ZIP, knapsack, digits, sales, weblog) | 8/20 | **19/20** | 11 / 0 (p = 0.0005) |
| REGRESSION (checklist, batch, workspace) | 14/17 | 15/17 | 1 / 0 |

| Family | Raw | Layer | Tokens, layer / raw |
| --- | ---: | ---: | ---: |
| tar+gzip bundle | 0/4 | 4/4 | 0.81 |
| ZIP archive | 0/4 | 3/4 | 0.87 |
| knapsack | 3/3 | 3/3 | 0.08 |
| digits | 1/3 | 3/3 | 0.76 |
| sales table | 1/3 | 3/3 | 0.43 |
| weblog | 3/3 | 3/3 | 1.11 (was 2.32 before input.txt) |
| checklist | 2/3 | 3/3 | 1.16 |
| batch, workspace (passthrough) | same | same | 1.00, byte-equal |


### Attribution: the same base model at a conventional 4-bit (T2)

Qwen3.8-27B UD-Q4_K_M, raw, on six of the P2 coding requests (identical prompts, Bonsai's chat template):

| | Bonsai raw | Bonsai + layer | teacher, 4-bit raw |
| --- | ---: | ---: | ---: |
| tar+gzip bundle, seeds 251-254 | 0/4 | 4/4 | 1/4 |
| ZIP archive, seeds 251-252 | 0/2 | 2/2 | 2/2 |

The teacher hand-rolls the tar format too (none of its four solutions import `tarfile`) and gets it wrong three
times; it recalls `zipfile` and passes both ZIP runs where raw Bonsai passes none. So: the habit of avoiding the
library is in the base model, the loss of library recall is the compression's, and the cards address both.


(A second attribution run against another lab's model was made on the same requests; it is not published here.)

## Round 10 (2026-10-03): a public benchmark, paired (A1)

AIME 2025, 30 problems, one request each, same seed, raw server vs the layer (plain request, so the model gets
the sandboxed Python tool).

| | Raw | Layer |
| --- | ---: | ---: |
| AIME 2025 correct, seed 1 | 26/30 | 29/30 |
| AIME 2025 correct, seed 2 | 26/30 | 27/30 |
| pooled, 60 pairs | 52/60 | **56/60** |
| rescues / losses, pooled | | 6 / 2 |
| completion tokens | 706k | 827k (1.17x) |

The pre-declared pooled gate (>= 3 rescues, <= 1 loss) is **not met** (two losses), so the layer is reported as
directionally positive on AIME, not as a claim. The pattern is stable across seeds: two problems are rescued on both
seeds, and one problem (29) is lost on both, each time by running the tool to the round cap and answering wrong
after the final nudge at 50k+ tokens. That cap-then-nudge path is the loop's one identified defect.

| HumanEval 164, medium thinking, temp 0 (HE1) | 159/164 | 160/164 | 2 / 1: neutral (gate not met) |

HumanEval sits at a 97% ceiling for this model and does not exercise library recall or long computation, so a
neutral result is the expected one; it also shows the layer does not get in the way of short coding requests.

| MATH-500, first 100 integer-answer problems, levels 1-5 (M5) | 99/100 | 100/100 | 1 / 0: neutral at a ceiling; tokens 0.83x |


### A regression found and fixed: code-executing agents (AW1)

AppWorld, 20 `test_normal` tasks, the public bench's `simplified_react_code_agent`, one pass each:

| | Raw | Layer (before the fix) |
| --- | ---: | ---: |
| tasks fully correct (TGC) | 13/20 (65%) | 4/20 (20%) |
| rescues / losses | | 0 / 9 |

The ReAct code agent sends plain chat and executes the model's code blocks itself. The layer saw "no client
tools", offered its sandboxed `run_python`, and the model ran its code there, where the agent's `apis` object does
not exist; 8 tasks ended after one call, 5 spun to the step cap. Fix shipped the same morning: a conversation that
already carries fenced code blocks and offers no tools is passed through untouched. Rerun on the fixed build
(AW1b): layer 15/20 vs raw 13/20, 2 rescues, 0 losses, and the layer touched none of the 273 responses; the +2 is
the harness's own run-to-run variance (4 of 20 tasks diverge between two identical configurations).

### The "do no harm" check on knowledge questions (K1)

MMLU-Pro, 100 questions stratified over 13 subjects, paired, one seed:

| | Raw | Layer |
| --- | ---: | ---: |
| correct | 71/100 | 76/100 |
| rescues / losses | | 10 / 5 (p = 0.30) |
| tokens | 486k | 389k (0.80x) |

Within noise on the pure-recall subjects (10 of the 15 discordant pairs are questions where the layer never used
its tool, so both arms simply drew different samples), a real gain on the quantitative ones (chemistry 5 -> 8,
physics 5 -> 6, engineering 6 -> 7) and on three questions where raw ran out of budget without an answer. No harm,
20% fewer tokens.

## Round 11 (2026-10-03 afternoon): the suite's own reference run (S1)

`suite/run_suite.py`, default plan, raw vs layer, 74 runs. Raw 17/37, layer **28/37**; 13 rescues, 2 losses;
tokens 0.74x (coding 0.88x, computation 0.40x, workspace 1.06x). The new self-contained tar contract moves 0/4 ->
2/4 and ZIP 1/4 -> 4/4; digits 0/3 -> 3/3, LCS 0/3 -> 2/3, sales 1/3 -> 3/3; knapsack and weblog already 3/3.
The two losses are a MIME swap at the model's floor (1/4 both arms) and one workspace pair that diverged in
sampling on a request the layer forwards untouched (9 of 10 such pairs reproduced token-for-token).

Second seed set (S2): raw 17/37, layer **29/37**; 13 rescues, 1 loss; tokens 0.67x. Pooled S1 + S2, 74 pairs:
raw 34/74, layer 57/74, 26 rescues, 3 losses. The suite README carries both scoreboards.

## Round 12 (2026-10-04 night): the two defects

| | result | decision |
| --- | --- | --- |
| E16, cap-then-nudge (AIME 13, 14, 29 x 3 seeds) | 8 rounds won 4 of 9 cells; 12 rounds won 7 of 9 and lost none the old cap won; a reasoning-oriented last message won 4 of 9 | `max_rounds` 12 shipped; the longer leash fixes the one-past-the-cap case and costs tokens on problems the loop cannot finish |
| E17, email delegation card (MIME x 6 seeds) | 0/6 vs 0/6 | not adopted; the MIME failures are validation and header content, not API names |

## Round 13 (2026-10-04): the full AppWorld set, the product as shipped (AW2)

168 `test_normal` tasks, the public bench's ReAct code agent, one pass, raw Bonsai 2 27B PTQ1_0 on this serve
(medium effort, budget 20480). The layer is not involved (passthrough on this client).

| | this serve, PTQ1_0 (1.75 bpw) | public figure, PQ2_0 (2.13 bpw), not reproduced here |
| --- | ---: | ---: |
| TGC | **70.8%** (119/168; 95% CI 63.6-77.2) | 64.3% |
| SGC | 46.4% | 42.9% |
| easy / medium / hard | 93.0 / 58.3 / 60.3 | 86 / 52 / 54 |
| failures by wrong format | 1 | 16 |
| failures at the step cap | 1 | 15 |

The pre-declared gate allows "matches" (lower bound above 55) and not "exceeds" (lower bound 63.6 against 64.3).
The serving-side failure classes are gone; what remains is the model.

### The 2.13-bpw container on the same run (AW2b)

Prism's stock PQ2_0 on this serve, same recipe: TGC 67.9% (114/168; CI 60.5-74.5), SGC 44.6%, 0 wrong-format and 0
step-cap failures. Paired with the PTQ1_0 run: 22 tasks one way, 27 the other. Same trits, different packing,
same score; the smaller file is the better download. Against the public 64.3% for this very file on the stock
fork, the serve recipe is consistent with a modest lift and removes the serving-side failure classes entirely.

