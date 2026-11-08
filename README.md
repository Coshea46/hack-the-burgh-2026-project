# Touchline

Touchline plays independently hosted football videos and uses a backend director
to recommend a match. The default real model is the research-winning temporal GRU,
selected head **`shots3_10`**, pinned as
`temporal-shots3_10-d63fff64480d/classifier.pt`. Its released predictor, saved
normalization, runtime source hashes and corrected native-sample-clock audio
contract are used together. The original full-audio GRU remains an explicit
`--model legacy` rollback; failed readiness never silently changes models or
substitutes mock scores.

Touchline is the product name. Existing `MATCHPULSE_*` environment settings,
`matchpulse-*` resources, runtime package names and protocol headers retain their
technical names for compatibility.

**Production policy caveat:** the unchanged Balanced director's raw-score bonus
and confirmations differ from the research evaluation policy. The new model's
research result does not establish useful automatic switching in this app. The
offline production-policy replay below shows that Balanced rarely switches;
All Action behaves differently. Scores are uncalibrated, not goal probabilities.

The selected release is deployed to **`matchpulse-inference`**. Canonical cloud
readiness passed, including the real release fixture (score error `4.66e-08`).
Six direct-S3 overlap windows matched the independent reference exactly, including
corrected audio. A new 30-second seven-source test delivered **13/13 complete
score cohorts**, with 1.734–2.109s observation-to-WebSocket latency (median 1.859s)
and no three-second deadline misses. Owned worker shutdown was confirmed.

Edge verified initial football playback, Auto becoming On after readiness,
seven-source model scores, a server-acknowledged mode change, and actual ElevenLabs
commentary. After fixing a missing `loadeddata` readiness event and a bounded
multi-shard startup barrier, the real browser committed two natural All Action
switches: Chelsea–Swansea to West Brom–Chelsea at replay 12.925s, then back at
20.865s. Both were actual player acknowledgements, not a headless viewer or
injected scores. Manual selection also preserved the common replay position.

The final browser run produced nine recommendations before a Windows progress-file
replacement error ended it at 54.8s; owned cleanup succeeded. Progress telemetry
is now best effort so that a locked optional receipt cannot interrupt viewing.
That final CPU-only error fix is regression-tested rather than claimed as another
paid cloud run. This is bounded browser evidence, not a long-session or
frame-perfect synchronization certification. Task receipts are ignored under
`artifacts/winning-model/`; policy replay details are under
`backend/ml_inference/artifacts/winning-model/`.

Model-integration checks at completion: **779 Python tests passed, one optional local Torch/runtime test
skipped; 136 frontend tests passed; the production build and backend Ruff passed**.
Separate installed-runtime checks passed 18 tests, and canonical cloud readiness
was rechecked after the final inference deployment. Estimated incremental Modal
compute was **$1.80 of the $3 task allowance**, including conservative deployment
reserves. All inspected inference pools ended with zero containers, inputs and
backlog. Estimates are planning records, not a provider invoice or billing cap.

### Local connection and audio repair

For ordinary viewing, use `backend.local` below. The finite `backend.demo`
verification command shuts down both WebSocket and HTTP when its timer ends;
using it as a permanent backend disconnects captions, Tables and News. The local
launcher keeps those services alive after paid inference finishes, without
renewing inference or caption allowances. Frontend defaults now match ports
8030/8031. Failed metadata connections retry with bounded backoff and recover
when the backend reconnects; provider quota/setup failures remain distinct.

Real football-data.org standings and twelve Guardian articles were verified over
HTTP and rendered in Edge during this repair. Obsolete verification tabs that
were also playing audio were closed. Preview players enforce mute, while updated
tabs on the same origin use an exclusive browser audio lock. Use **Play audio
here** to transfer sound to another tab. Different origins/ports and old cached
copies cannot share that lock; close or refresh those copies. Exclusive audio
requires a supported secure browser context, including localhost or HTTPS.

The approved caption allowance is now eight hours with a $3.60 estimated budget,
independent of the finite GPU monitoring period. Expired allowances retain their
actual reason through reconnects and switches instead of becoming a misleading
connection prompt. API keys remain backend-only.

Latest repair checks: **828 Python tests passed, one optional runtime test skipped;
167 frontend tests passed; production build and Ruff passed**. Edge displayed
genuine live commentary, and a twelve-second real ElevenLabs observation received
nine partial and two committed transcript events for the manually selected match.
Only one audible Touchline tab remained. The current eight-hour bound is
verified with fake-clock tests, without consuming eight hours of paid audio.

Long provider utterances now retain their actual latest text/word suffix within
the browser and IPC limits instead of being silently dropped. Absolute word
timestamps are preserved. The sidebar bounds its caption text height and follows
the latest text so long commentary does not push the match grid down the page.

The older seven-source 28/28, 60-second result below belongs to the **legacy
model**, not the new release. Explicit `features_mock` remains a deterministic
switching demo with labelled synthetic scores. Existing UI, provider and caption
evidence is retained with its original scope.

## Frontend design

The public navigation contains **Watch, Tables and News**. The frontend follows
the transparent navigation, rounded active tabs, soft multicolour gradients and
frosted cards of [EdinburghAI Hub](https://edinburghai-hub.osheaconboy.chatgpt.site/),
adapted around football playback. Its published desktop preview was inspected;
the reference site itself returned 403 to the web reader. No changes were made
to the reference Site.

Light is the default theme; an explicitly saved dark preference is retained.
Inter 4.1 is served locally as a variable WOFF2, with a preload, `font-display:
swap`, system fallbacks and its SIL Open Font License in `public/fonts/`. The
header contains the Touchline wordmark, three navigation links and a theme
toggle. Connection and provider errors appear beside the affected controls or
media rather than in a permanent navbar indicator.

Watch places the main video beside a compact sidebar on desktop, with commentary
captions directly below Auto Director. Both panels stack below the video on mobile.
Six alternative matches appear underneath the main row in a responsive grid.
There are no replay/selection badges or caption size/position controls. There is
no marketing hero. Tables puts
league search and standings first; News uses a responsive article-card grid.
The Moments and About frontend pages, navigation state and components are removed.
Backend selection history and telemetry are preserved. Essential replay,
experimental-model and machine-caption disclosures remain in context.

### Earlier Watch layout verification (2026-11-08)

The focused layout update passed **128 frontend tests across seven suites**, the
CI production build and application build lint. Regression coverage preserves
manual/automatic switching, mounted media, caption alignment and On/Off behaviour;
it also checks page order and that old caption size/layout preferences are unused.
Edge inspection confirmed the desktop player/sidebar, three-column alternatives
underneath and fixed captions after the grid. At 320 CSS pixels, Director controls
stack below the video and alternatives use two columns without visible overflow.
A real manual match change retained paused playback at **427.433 seconds**. The
preview was left on Watch, paused, with captions On. Real GPU automatic switching
and paid transcription were not rerun for this layout-only update; backend and
Modal code are unchanged.

### Earlier redesign verification (2026-11-08)

The final frontend passed **126 tests across seven suites** and its CI production
build. New regressions check the three-link navigation, safe redirects from old
Moments/About URLs, keyboard controls and video-element identity, source, time,
rate and volume across page changes. Existing switching, WebSocket and live-caption
tests remain in the suite. Relevant Python director, replay, caption-session,
provider/API and WebSocket integration tests passed **199 tests**. No backend
runtime or ML architecture changes were needed for this redesign.

Application build lint passed. The targeted test-file ESLint pass allows four
test-style rules for direct DOM continuity assertions and asynchronous fixtures.
axe-core reported zero structural WCAG 2 A/AA and 2.1 AA violations in light and
dark Watch tests; JSDOM cannot measure rendered colour contrast, so this is not a
complete accessibility certification. The locally served Inter font returned
HTTP 200 with the correct WOFF2 content type and the official asset's SHA-256.

Edge browser checks covered the transparent three-link header, light/dark themes,
actual football playback, six alternative feeds, genuine football-data.org
standings and Guardian article cards. Responsive emulation at 390 and 320 CSS
pixels covered Watch navigation and caption controls; Tables and the single-column
News layout were also inspected at 320 pixels. Caption position and text-size
controls remained readable at that width. This was desktop Edge emulation, not
physical-device or cross-browser testing.

The paused primary video retained its **231.895-second** position through Tables,
News and back to Watch. The preview was left in light mode on Watch, paused, with
captions On and the factual "Live captions pause with the player" message. Earlier
theme changes also preserved advancing playback. Structural tests cover the
additional media-state invariants; browser inspection alone does not establish
frame-perfect synchronisation.

Visual QA used a seven-source CPU backend with inference monitoring disabled,
which the controls accurately displayed as "Monitoring off". Live Modal switching
and paid ElevenLabs transcription were not rerun for this styling change. The
previous real-audio and GPU evidence below remains historical evidence. No Modal
deployment or paid transcription was started for this redesign; additional
estimated paid compute/transcription spending was **$0**. Complete seven-source
real-model browser acceptance, measured browser contrast and physical mobile
testing remain outstanding.

## Football platform: fixtures, Tables, News and commentary captions

Watch keeps one full-source native video player per registered match (seven for
the demo). Selecting a match promotes that same already-decoding player with CSS;
it does not replace its source URL, recreate the element or seek an aligned warm
player. Only the focused source can output audio, and the tab retains its audio
lease while changing the focused player. Captions follow its actual native clock.
Automatic proposals for an unready or misaligned destination are discarded while
the current video remains visible; a later fresh prediction can select it.
Manually selecting an unbuffered source, or a preview that was paused, can still
require loading/realignment. Pausing previews trades immediate readiness for less
decoding work. Small drift is corrected gradually while previews play.

At a ready source handoff, the backend accepts up to 150ms of backward native
clock drift without treating it as a seek. It records the real destination time.
Same-source backward seeks retain the existing strict detection, and larger
handoff jumps still reset the replay epoch and invalidate old predictions.

An isolated, muted Edge browser check using the seven actual S3 recordings
observed three warm manual switches with the next decoded frame arriving
42–144ms after pointer-down. Each retained all seven native elements, performed
no destination source/load/seek/play/pause operations, and kept one audible
source in the browser state. A 390px viewport retained seven players, stacked the
sidebar below the main video and placed alternatives underneath without overflow.
Automatic readiness/ACK behaviour and caption source changes are also covered by
the frontend tests; that browser timing measurement covers manual warm handoffs.

The three navigation pages are **Watch, Tables and News**. The
player/session stays mounted across pages; main playback continues and alternative
previews pause when Watch is hidden. News and standings use a separate bounded
HTTP API, not the inference socket or GPU workers. No account is required to view
the site. Theme, director mode, league and caption preferences stay in the browser.

### One source-bound fixture catalog

The canonical configuration is
`frontend/sports-streaming-service/src/data/matches.json`. Both the React bundle
and Python source registry read this one file; the backend Docker image explicitly
packages it. Original `cam-1` through `cam-7` object associations are unchanged.

| ID | Fixture |
|---|---|
| cam-1 | Chelsea vs Swansea City |
| cam-2 | Manchester City vs Chelsea |
| cam-3 | West Bromwich Albion vs Chelsea |
| cam-4 | Chelsea vs Crystal Palace |
| cam-5 | Liverpool vs West Ham United |
| cam-6 | Manchester City vs Watford |
| cam-7 | Swansea City vs Manchester United |

Match 7's broadcast scoreboard reads `SWA` versus `MU`, with United's red kit;
the historical fixture is corroborated by the
[official Swansea City report](https://www.swanseacity.com/news/30082015-1500-v-manchester-united).
Object ETag, byte length and a signed-query-independent locator digest bind the
metadata and caption tracks to their source. Multipart ETags are identity tokens,
not claimed SHA256 file checksums. Custom sources do not inherit demo identities
merely because they reuse `cam-1`.

Replay scores are **historical metadata**, separate from current-season Tables.
The six other sources show 0–0 in the inspected source interval `[120,600)`.
Liverpool vs West Ham shows 0–0 for `[120,150)` and 0–1 for `[160,600)`; the
uncertain 150–160-second boundary is deliberately unscored. The
[official Liverpool report](https://www.liverpoolfc.com/news/first-team/192900-reds-beaten-by-hammers-at-anfield)
also confirms the early West Ham goal. Scoreboards were inspected in the actual
S3 footage; no fixed 0–0 remains beyond verified coverage. Before source120,
after source600, and inside the uncertain transition, the fixture appears without
an asserted score. Source times are native media seconds, not replay-clock seconds.
Replacing an S3 object requires re-verifying its identity and replay metadata.

### Provider configuration

Copy `.env.example` to ignored repository-root `.env` and configure only the
providers you want. Existing process environment values take precedence. The
backend reads literal values without shell expansion and never sends these keys
to the frontend. Restart the backend and refresh the page after changing keys.

| Variable | Setup |
|---|---|
| `FOOTBALL_DATA_API_KEY` | Register for a permitted free plan at [football-data.org](https://www.football-data.org/client/register), then copy its token locally. |
| `GUARDIAN_API_KEY` | Request a permitted developer key through [Guardian Open Platform](https://open-platform.theguardian.com/access/). |
| `ELEVENLABS_API_KEY` | Create a scoped speech-to-text key in your authorised [ElevenLabs workspace](https://elevenlabs.io/app/developers/api-keys). Check the workspace allowance and key cap locally. Used only by the server-side caption worker. |

No subscription or paid plan is purchased by this application. Without credentials,
Tables and News show honest connection/setup states; no sample rows or articles
are substituted. Live captions default to **On**: a configured ElevenLabs key
automatically starts transcription when the focused video plays. Stored tracks
remain an optional offline tool.

Tables proxies the current football-data.org v4 API. The eight default leagues
are Premier League, La Liga, Bundesliga, Serie A, Ligue1, Championship, Eredivisie
and Primeira Liga. Optional Champions League standings preserve the provider's
group/league-stage structure. A local alias/fuzzy index supports natural league
and club queries; current club membership comes from real cached standings, not
the historical replay fixtures. Ambiguous clubs are offered as choices. Missing
statistics remain unavailable. Standings cache for 15 minutes; provider calls
share a process-level 10/minute limit and respect provider retry-after responses.
See [v4 policies](https://docs.football-data.org/general/v4/policies.html).

News uses Guardian football metadata, topic filters and search. It deduplicates
and sorts actual articles by publication time, links to the publisher, and retains
byline/copyright plus linked official Guardian attribution. The default integration
requests no article body, excerpts or imagery whose reuse permissions are uncertain.
Its cache is 10 minutes with an absolute 24-hour purge in backend and frontend;
cached responses are labelled. Limits are 1 request/second and 500/UTC day for the
developer tier. Other applications using the same keys also consume provider
allowances. Review [Guardian access](https://open-platform.theguardian.com/access/)
and [terms](https://www.theguardian.com/open-platform/terms-and-conditions).

### Live commentary: ElevenLabs Scribe v2 Realtime

The Watch caption panel uses **`scribe_v2_realtime`**, through the official
[ElevenLabs server-side WebSocket SDK](https://elevenlabs.io/docs/eleven-api/guides/how-to/speech-to-text/realtime/server-side-streaming).
It streams actual commentary from the focused source as that video plays. This is
live transcription of prerecorded demo footage, not a precomputed caption replay.
The other six feeds continue ML monitoring without opening caption connections.

The backend passes validated native player positions to an isolated caption
subprocess. It decodes authorized S3 audio into mono 16 kHz PCM and sends small
chunks only up to the last reported playback position. It does not give the provider
the complete video URL or stream future match audio. Clock reports expire after
five seconds. Pauses, stalls, seeks, controller disconnects and match switches stop
the old source; generation and clock-epoch checks discard late text. Only one
provider connection exists per viewing session. Caption work never enters Modal or
blocks the director's two-second prediction cadence.

Partials appear immediately, labelled as provisional; committed text replaces
them. Committed word timestamps are provider times plus the exact source-audio
anchor. Partials have no invented word times. The accessible panel has an On/Off
control and a fixed sidebar panel with readable responsive text. Caption size
and overlay preferences are no longer used. Silence produces no invented text;
crowd noise can reduce recognition quality. This integration does not infer goals,
speaker identities or crowd events that Realtime did not return. There is an
unavoidable recognition delay after audible speech; the application does not
artificially delay football playback to conceal it.

Open Touchline and start watching: captions start automatically when the backend
has `ELEVENLABS_API_KEY` and the isolated caption runtime is installed. No caption
launch or approval flag is needed in local operation or Docker. The former
`MATCHPULSE_CAPTION_LIVE_AUTHORIZED` setting is obsolete and ignored, including
an old `false` value in a local `.env` or launch environment.

The session controller's **Commentary captions** toggle stops audio transmission
immediately when turned Off. That choice survives match switches, seeks and
reconnections in the same replay session. Turning captions back On resumes from
the current playback position. A new replay session defaults On. Pauses, buffering
and unavailable sources stop the stream until valid playback resumes. Missing
keys, rejected credentials and missing Speech to Text permissions show explicit
setup/error states rather than a simulated listening indicator.

Install caption dependencies separately, preserving inference dependencies:

```powershell
& backend/ml_inference/.venv-deploy/Scripts/python.exe -m venv backend/.venv-captions
& backend/.venv-captions/Scripts/python.exe -m pip install -r backend/requirements-captions.txt
# Read-only allowance check. Never paste the key into terminal commands or chat.
& backend/.venv-captions/Scripts/python.exe -B -m backend.captions --account-check
# Check this exact key's Realtime permission without streaming or uploading audio.
& backend/.venv-captions/Scripts/python.exe -B -m backend.captions --realtime-access-check
```

The SDK requires a newer WebSocket library than the proven inference backend;
the subprocess uses its own pinned environment. Set `MATCHPULSE_CAPTION_PYTHON`
to that environment's Python (Windows example in `.env.example`; on Linux use
`backend/.venv-captions/bin/python`). The Docker image builds a separate
`/opt/matchpulse-captions` environment automatically. No permanent key is sent to
React or embedded in a build. Do not expose this unauthenticated demo backend to
the public internet; origin restrictions are not user authentication or a global
billing limit.

Before a bounded demonstration, check current
[API pricing](https://elevenlabs.io/pricing/api), remaining workspace credits, this
key's speech-to-text permission/cap and any concurrent account usage. Subscription
credits alone do not prove an API-key-specific allowance. The published base rate
checked on 2026-11-08 is **$0.39/hour**: eight hours is approximately **$3.12**
before taxes, billing rounding and account-specific terms. This is an estimate,
not a provider-enforced dollar cap. No editing/keyterm premium or subscription
purchase is enabled.

The read-only account command requires the key's `user_read` permission. A scoped
speech-to-text key can lack that permission; a 401 `missing_permissions` response
does not establish that the key is invalid. In that case verify the workspace and
key allowance in the dashboard locally instead of broadening permissions solely
for the demo. Never continue with an unverified allowance.
The Realtime access check uses the official SDK to mint and immediately discard a
short-lived token; the token is never printed or saved, and transcription is not
started. `provider_permission_speech_to_text_missing` means the configured key
needs Speech to Text access in the provider dashboard. This check does not verify
remaining credits or purchase anything.

The approved normal-viewing caption defaults are an **eight-hour deadline from first valid
active playback**, at most 28,800 aggregate seconds of provider connection/audio,
and **$3.60 estimated cost**, across switches/reconnects/toggles. Set
`MATCHPULSE_CAPTION_MAX_AUDIO_SECONDS=28800` and
`MATCHPULSE_CAPTION_BUDGET_USD=3.60` in root `.env`. Shorter allowances remain
supported. Restart the backend after changing these settings; an existing
session keeps its original deadline. Pausing does not extend the session deadline. The viewer
toggle defaults On in a new session. Exhaustion stops the
connection and reports the limit rather than silently starting another stream.
Off/On and reconnecting do not reset the deadline or the worker's cumulative
consumption. The optional `MATCHPULSE_CAPTIONS_ENABLED=false` service setting can
disable captions entirely; its default is true. These controls complement a
provider-side spending cap. A longer duration or higher budget requires another
explicit policy change; no reconnect automatically renews paid transcription.

The optional offline `python -m backend.captions` utility uses batch `scribe_v2`
and persists source-bound JSON/WebVTT under ignored `backend/artifacts/captions/`.
It defaults to an estimate and requires `--execute` for a bounded paid job; it is
not the Watch experience. The read-only track API never transcribes on a GET.

### Keep the local website running

Use the persistent local backend for ordinary viewing. It serves the browser
WebSocket on 8030 and the Tables/News/caption HTTP API on 8031 until you press
Ctrl+C. Inference expiry does not disconnect the website. From the repository
root, start the website with real monitoring prepared but no GPU running:

```powershell
& backend/ml_inference/.venv-deploy/Scripts/python.exe -B -m backend.local
```

Click **Auto On** in the Watch page to start the installed real model at the
actual current replay position. The controlling viewer can start it; observers
cannot. The switch shows starting until the configured model and all worker
shards are ready. Turning Auto Off before submission cancels that request;
after submission it stops automatic switching while monitoring continues.

To start the same bounded monitoring automatically when playback connects:

```powershell
& backend/ml_inference/.venv-deploy/Scripts/python.exe -B -m backend.local --allow-cloud --seconds 2400 --budget 10
```

The normal launcher reads the existing app-only private WebSocket credentials
without opening a GPU connection. Missing credentials leave a truthful unavailable
state. Starting from the button or `--allow-cloud` uses the same selected model,
source bindings and a **40-minute / $10 estimated service allowance** by default,
following the authorized removal of the earlier two-minute demo limit. `--seconds`
can be set up to 3,600 and `--budget` up to $20; the existing deployed per-worker
allowance stays capped at $10 while the backend partitions the overall ceiling;
short bounded validation commands remain supported. It does not
deploy a worker or access research files. There are no automatic paid restarts.
The first start fixes the service deadline; duplicate clicks and reconnects do
not renew it. An early stopped input can restart only after a new explicit On
request, with at least five seconds and enough unreserved budget remaining.
All input reservations accumulate against the original allowance. Terminal
model errors stay unavailable. After expiry the browser shows monitoring stopped;
manual playback, Tables, News and the local connection continue. Reconnecting
does not renew inference or captions. Live captions remain independently bounded
to the approved eight-hour/$3.60 allowance and show their exhausted status after
that limit. Use `--offline --no-captions` for a provider-free CPU check with no
ability to start cloud inference. With locally
configured keys, the default command can use those bounded captions even when
GPU monitoring has not been started.

In a second terminal:

```powershell
$env:PORT = '3030'
$env:BROWSER = 'none'
$env:REACT_APP_WS_URL = 'ws://127.0.0.1:8030'
$env:REACT_APP_API_URL = 'http://127.0.0.1:8031'
npm --prefix frontend/sports-streaming-service start
```

Open <http://127.0.0.1:3030/> and keep both terminals running. The local launcher
sets matching localhost/127.0.0.1 origins and accepts `--port`, `--api-port` and
`--frontend-port` overrides. Frontend API/WS URLs are build-time settings.

The backend shares one replay session across connected tabs. The first tab gets
playback/director control; additional tabs can watch. If an older tab already
owns the session, click **Use this tab** in Auto Director to transfer control and
audio to the current tab. The backend acknowledges ownership before enabling the
controls. Old-tab writes are rejected, and it releases its audio output. This
handoff preserves the session, worker group and original inference/caption
allowances; reconnecting an old tab never automatically takes control back.
After updating the backend for this capability, restart it once and refresh the
frontend. An older backend reports that a restart is needed for control handoff.

`python -m backend.main` remains the environment-configured server entry point;
Docker Compose publishes3000/8000/8031 on loopback by default. Build the backend
with root context (`docker build -f backend/Dockerfile .`). The separate
`backend.demo` command below is a finite validation harness: it shuts down its
CPU server when its duration ends, so use `backend.local` for ongoing viewing.

### Expansion verification (2026-11-08)

The full backend/ML suite passed **664 tests**. The frontend passed **118 tests**
across six suites and a CI production build; backend Ruff passed.
These checks include real loopback WebSocket control and delivery, source switching,
clock epochs, stale partial rejection, pauses, buffering, seeks and trial limits.

Actual authorized S3 audio from cam-1 and cam-2 passed progressive decoder probes:
120.000–122.999 source seconds, 2.999 seconds of mono 16 kHz PCM each, contiguous
within one output sample, with no submitted samples beyond the supplied viewer
watermark. The real isolated caption subprocess passed an unpaid IPC/clean-shutdown
probe with authorization disabled and zero provider sessions/audio.

Real football-data.org validation returned 20 current Premier League teams; real
Guardian validation returned 12 articles. Repeated reads used the cache. The seven
registered source identities and inspected historical scoreboard intervals were
verified against the original footage. The inference worker files remain unchanged.

**Real ElevenLabs live transcription passed** after the operator enabled the
configured key's `speech_to_text` permission. The successful 18-second paced
headless run streamed actual cam-1 football audio, switched to cam-2, and received
9 partial updates plus 6 committed events (3 segments, each followed by its word
timestamps). No caption text belonged to the wrong active source. The run used
two sequential provider connections, 15.810 seconds of PCM and 14.515 seconds of
connection/handshake time, with zero errors and confirmed clean shutdown.

Committed caption lag against the replay clock was **1.140–1.344 seconds**, median
**1.277 seconds**, across three timestamped segments. This is receipt source time
minus the provider's final word-end timestamp, not an audio-device measurement.
Initial connection to first text took **6.016 seconds**; switch to first text from
cam-2 took **2.297 seconds**. These are small-sample integration measurements, not
accuracy guarantees. Caption text was not independently human reviewed.

Real testing also exposed and fixed fractional native-sample continuity and early
SDK event capture. Including three earlier diagnostic attempts, the entire trial
used **26.061 connection/handshake seconds**, **16.308 seconds of PCM**, and about
**$0.00283** at the published base connected-time estimate. Every owned connection
closed cleanly. Provider invoice amount and credit deduction are unverified: the
operator confirmed at least 1,000 credits and no separate key cap, while the scoped
key intentionally lacks `user_read`. No Modal resources were started or redeployed.
Ignored evidence lives under
`backend/ml_inference/artifacts/platform-expansion/live-caption-summary.json` and
`live-caption-validation.json`; it contains genuine provider events and timings,
not credentials. Those measurements preceded the default-On update; the ordinary
application now starts captions automatically with a configured key and active
focused playback, under the same session limits.

The default-On change also passed a new **25-second real-football test** through
the ordinary backend WebSocket. It sent no initial caption activation command and
left the obsolete launch flag false: captions still started automatically. Turning
Off stopped audio and provider connection consumption; turning On resumed from
the current source position. The run received 15 partial updates and 4 committed
events with no provider errors. Two sequential connections used 19.732 seconds of
PCM and 18.421 connection/handshake seconds (approximately $0.00200 base estimate),
then closed cleanly. Evidence is in the ignored
`backend/ml_inference/artifacts/platform-expansion/caption-defaults-validation.json`.
Browser automation reports its access host unavailable, so this expansion's visual
and audible playback behavior has not been interactively verified. Docker CLI is
unavailable here; the updated Docker build is documented but unbuilt locally.

## Seven-match demo and director modes

The product demo registers the seven existing distinct `cam-1` through `cam-7`
sources at original source offset 120 seconds. After the current release has been
deployed and its readiness verified, use these two PowerShell terminals from the
repository root. The backend command selects the new model, Balanced mode and
Auto Director On by default:

```powershell
& backend/ml_inference/.venv-deploy/Scripts/python.exe -B -m backend.demo --allow-cloud --matches 7 --seconds 120
```

In another terminal:

```powershell
$env:PORT = '3030'
$env:BROWSER = 'none'
$env:REACT_APP_WS_URL = 'ws://127.0.0.1:8030'
$env:REACT_APP_API_URL = 'http://127.0.0.1:8031'
$env:REACT_APP_TEST_VIDEO_KEY = ''
$env:REACT_APP_TEST_PREVIEW_KEY = ''
npm --prefix frontend/sports-streaming-service start
```

Open <http://127.0.0.1:3030/>. The focused source occupies the main player and the
other six remain available as alternatives. This uses the selected real model and
existing private inference credentials; it incurs bounded paid inference. The
backend WebSocket listens on 8030 and the Tables/News/caption HTTP API on 8031.
It exits after 120 wall-clock seconds, including startup, and starts no GPU until a
controlling viewer reports the actual player clock. Auto Director can be On while
waiting for worker readiness or fresh scores; On does not guarantee a switch.
Initial playback buffers while the detector, selected-model readiness and source
readers prepare. A saved browser director preference may restore a different mode.
Use `--offline` instead of
`--allow-cloud` to review the same seven source registrations with monitoring
disabled. Use `--matches 2` for a smaller run; the original bounded
`backend.ml_inference.overhaul_browser` two-match test is also preserved.

For an explicit rollback, add `--model legacy` to the backend command. It selects
`gru-stage1-02de8309/classifier.pt` and its original audio contract. Missing files,
checksum/source mismatches, incompatible schemas or failed fixture parity report
readiness errors; there is no implicit legacy or mock fallback.

The demo accepts 1–7 matches and a finite 30–180-second lifetime. Its default
per-launch estimated ceiling is **$1**; `--budget` may explicitly select $0.01–$3
but must cover the configured duration and GPU count. Seven sources use four T4s
(2+2+2+1), with a conservative 120-second reservation of about **$0.516** including
startup/shutdown allowance. Each explicit launch writes its own run receipt and
budget under ignored `backend/ml_inference/artifacts/product-polish/runs/`; earlier
verification ledgers are historical records, not a lifetime quota. Backend group
restarts are disabled for this finite demo, and uncertain stops retain their full
reservation. These are application estimates, not provider-enforced billing caps.
Live captions have their separate eight-hour/$3.60 session bounds described above.
The browser launch command should run only once at a time. The separate 3030/8030
ports avoid attaching an old two-match viewer to the new session; `--port` and
`--frontend-port` and `--api-port` can override them together with the frontend environment.

The backend enforces these initial director heuristics:

| Mode | Automatic switch cooldown | Current-match bonus | Consecutive challenger wins |
|---|---:|---:|---:|
| Relaxed | 20 seconds | 0.25 | 3 |
| **Balanced (default)** | **12 seconds** | **0.20** | **2** |
| All Action | 4 seconds | 0.05 | 1 |

The model continues evaluating every two seconds in every mode. A challenger must
beat the current score including its noncumulative staying bonus on consecutive
fresh completed endpoints. Duplicate and stale messages do not add confirmations.
Changing challenger, regaining the lead, manual selection and clock/session resets
clear confirmation state. An automatic selection starts its cooldown when
acknowledged as displayed. The same conservative guard also follows factual
playback source changes, so a slow or expired handoff cannot trigger an immediate
second move; expired proposals remain rejected. Scores continue updating throughout the cooldown.
Manual choices remain immediate and activate the existing 30-second hold. Turning
Auto Director off keeps monitoring active and suppresses automatic selection.
An optional backend strong-margin bypass is disabled by default; these
uncalibrated scores are not goal probabilities.

The mode selector uses the existing backend WebSocket, takes effect without a
worker restart and remembers the preference locally. Watch shows contextual
monitoring state and a brief prerecorded-replay disclosure. The backend retains
session-scoped factual selection history for telemetry; there is no standalone
Moments or About page. Model scores are relative, uncalibrated values; neither
goal labels nor team/scoreboard metadata are fabricated.

The controlling viewer sends
`{"type":"director_mode","session_id":"…","mode":"balanced"}` (also
`relaxed` or `all_action`). The server validates the preset and ownership, and
returns its authoritative `director` state. This includes the active configuration,
fresh-score timestamps, challenger confirmations, cooldown, selection reason and
at most 100 committed selection-history entries. Environment defaults are
`MATCHPULSE_DIRECTOR_MODE=balanced`, `MATCHPULSE_DIRECTOR_EMERGENCY_ENABLED=false`
and `MATCHPULSE_DIRECTOR_EMERGENCY_MARGIN=0.50`. The margin option bypasses only
confirmation, never manual control or cooldown. All three mode presets are UX
heuristics; none is claimed to be empirically optimal.

### Selected model versus the production director

The winning release is a 4,179-parameter, three-head temporal GRU. Production uses
only `shots3_10`: shots on/off target or goals in the defined 3–10-second lead
window. It observes the previous five seconds of raw float32 `(75,215)` features
at 15 FPS and advances every two seconds. The released code transforms these into
34 observed-value channels plus 34 validity bits, applies saved training-only
normalization and runs the 68-input/16-hidden GRU in evaluation mode. Visual
channels `0:210` are preserved; channels `210:215` use the released v3 decoder and
explicit audio-availability masks. Shape compatibility alone is insufficient.

`python -B -m backend.ml_inference.evaluate_director` replays the application's
actual unchanged Director on four official validation matches. At an **assumed**
2.157-second backend arrival delay plus 0.25-second display/ACK delay, selected
Balanced showed 27/138 qualifying events, 15/92 shots and 0/12 goals, with only two
switches across about 89.75 minutes. Selected All Action showed 70/138 events,
46/92 shots and 8/12 goals at 2.451 switches/minute and 24.37-second mean dwell.
Of those eight goals, five followed a switch 0–10 seconds before the goal; three
were already being viewed more than ten seconds earlier. Being on-screen is not
the same as predicting a goal.

These are conditional replay results, not held-out accuracy or newly measured
seven-stream latency. Validation already influenced research selection. They
assume synchronized, healthy playback, fixed delay and a common initial match;
stalls, faults, jitter and initial-choice bias remain limits. The original GRU
comparison uses the same repaired inputs, so it is not a reproduction of its old
serving output. Raw sigmoid-score bonuses differ from the research replay's
causal-centered log-odds policy; no centering, calibration or mode tuning was added.
Full results and fixed-stay references are recorded locally in
`backend/ml_inference/artifacts/winning-model/director-evaluation.md` and `.json`.

## Earlier director/UI verification (historical)

The updated full Python suite passed **488 tests**, including real local WebSocket
mode changes with seven unique registered sources, confirmation/cooldown cases,
health-loss and expired-ACK races, terminal worker states and bounded shutdown.
Ruff and `git diff --check` passed. The inference deployment and seven checked core
ML modules were not changed; no Modal redeployment was needed.
The frontend passed **61 tests across four suites**, including seven-source DOM
identity, server-confirmed modes, readiness-gated ACKs, explicit failed-player
fallback, manual hold/Auto off, freshness and factual history. Its final CI
production build passed. Responsive layouts and both themes are implemented;
the limits of actual browser observation are stated below.

Read-only requests verified all seven original videos and their seven configured
previews: each returned HTTP 200 and supported byte ranges, with distinct ETags.
Those checks establish availability, not independent proof of preview alignment.

The redesigned light theme, football playback and six alternative controls were
observed in Edge. Navigation automation then stopped because Computer Use could
not confidently determine the Windows browser URL. Separately, the seven-source
offline backend recorded a real browser connection, progressing playback and
manual selections without resetting the replay position. Full interactive mode,
theme, responsive and real-model auto-switch checks were not completed here.
The previously working two-match automatic demo was confirmed by the user.

The connected-browser shutdown test exposed a `websockets`/Python shutdown-order
cycle. Closing viewer sockets before draining the server fixes it; stalled peers
have a bounded abort fallback. The repeated 30-second, seven-source offline demo
exited after **30.004 seconds**, with socket shutdown complete. Both receipts are
preserved under ignored `backend/ml_inference/artifacts/product-polish/`.

No paid Modal verification was launched for this product update: estimated new
Modal compute is **$0**, and all checked inference pools had zero containers,
inputs and backlog. The dedicated $2 verification allowance remains available.
The frontend dev server on 3030 is available for review; the bounded backend has
exited. Main and preview video DOM nodes remain mounted during selection, mode,
theme and navigation changes. This earlier implementation reloaded the main
source on selection; the persistent source-player handoff described above replaces
that path. Only genuinely unready sources require buffering.

## Implemented data path

```text
S3 encoded video/audio ──→ browser player
          │                    │ actual playback heartbeat
          └──→ Modal replay    ↓
               worker ──→ CPU backend director ──WebSocket──→ browser selection
```

The CPU backend registers sources, coordinates replay time and selects matches.
It never decodes or uploads five-second RGB arrays. Up to four physical GPU workers
multiplex independent source decoders and feature caches. The default is one T4
per two sources: seven sources use four T4s, balanced as 2+2+2+1.
`MATCHPULSE_GPU_WORKERS=1` through `4` overrides this within the registered source
count. Earlier seven-source attempts on one and two T4s missed cadence. A first
four-worker run also missed early windows; decoder priming and bounded reconnects
then enabled the final complete legacy-model 60-second run. This establishes
historical bounded capacity, not new-model or multi-hour reliability. Each source
samples at 15 FPS, assembles completed five-second `(75,215)` windows with aligned
16 kHz audio, and advances every two seconds. Overlapping windows reuse detections.
The obsolete backend array ingester and placeholder processor have been removed.

The frontend preserves its player, manual selection, automatic selection toggle,
reconnection and view transitions. Recommendations carry session/model identity,
clock epoch, sequence, observation endpoint, score kind and expiry. The backend
commits a displayed match after viewer acknowledgement or actual playback feedback.
The Balanced director uses a noncumulative 0.20 staying bonus, deterministic ties,
two fresh challenger confirmations, a 12-second automatic cooldown and a
30-second manual hold. Missing or stale scores do not
become invented probabilities.
If the displayed source becomes unavailable, fresh scores may recommend a healthy
fallback when automatic selection is enabled and the manual hold has expired.
An unavailable ML worker cannot override a manual choice of a playable source.
Auto Director off always preserves the viewer's manual selection.

## Play the videos without cloud inference

From the repository root, with Docker Engine and Compose installed:

```powershell
$env:MATCHPULSE_MONITOR = 'false'
$env:REACT_APP_WS_URL = 'ws://localhost:8000'
$env:MATCHPULSE_ALLOWED_ORIGINS = 'http://localhost:3000,http://127.0.0.1:3000'
docker compose up --build -d
```

Open <http://localhost:3000>. Monitoring defaults to `false`, so this command starts
the CPU control backend and static React frontend without starting a GPU. The
backend WebSocket is `ws://localhost:8000`. Both published ports bind to loopback
by default. No AWS credentials are needed for the existing public demo sources.

The frontend image builds with Node 24 and serves the production bundle through
nginx. `REACT_APP_WS_URL` is a **build-time** setting: rebuild the frontend after
changing it. The backend image uses Python 3.12 and needs no local GPU, FFmpeg or
OpenCV. Build contexts exclude local virtual environments, benchmark artifacts,
media and checkpoints.

## Run the selected model with Compose

The independent Modal application `matchpulse-inference` must already be deployed
in your Modal workspace. The default inference transport is a persistent private
WebSocket, authenticated with a dedicated Modal proxy bearer credential and the
inference application's own Secret. It avoids per-update Modal Dict round trips.
The CPU backend alone receives `MATCHPULSE_MODAL_WS_URL` and
`MATCHPULSE_MODAL_WS_TOKEN`; neither is sent to the browser, included in a frontend
build or exposed in public session snapshots.

The bounded deployment helper saves these values in the ignored private credential
file. Load them without printing their contents:

```powershell
$wsCredentials = Get-Content -LiteralPath 'backend/ml_inference/artifacts/overhaul/ws-credentials.json' -Raw | ConvertFrom-Json
$env:MATCHPULSE_REPLAY_TRANSPORT = 'websocket'
$env:MATCHPULSE_MODAL_WS_URL = $wsCredentials.url
$env:MATCHPULSE_MODAL_WS_TOKEN = $wsCredentials.token
```

Alternatively provide those two variables through your secret manager or ignored
root `.env`. Monitoring with this transport requires a deployed `wss://.../session`
endpoint and its matching token. Host Modal CLI login files are not mounted into
Docker; this transport needs no workspace SDK credentials in the running backend.
Keep tokens out of logs and version control. Public sources need no AWS credentials
on Modal. `MATCHPULSE_REPLAY_TRANSPORT=dict` explicitly selects the older diagnostic
transport, which requires backend `MODAL_TOKEN_ID` / `MODAL_TOKEN_SECRET` instead.
The frontend always connects only to the local application backend WebSocket.

First complete the current deployment and selected-checkpoint readiness procedure
below. The selected path is `temporal-shots3_10-d63fff64480d/classifier.pt`; old
baseline readiness does not establish readiness for this model. Start with two
sources and one physical GPU:

```powershell
$env:MATCHPULSE_MONITOR = 'true'
$env:MATCHPULSE_ML_MODE = 'real'
$env:MATCHPULSE_ML_CHECKPOINT = 'temporal-shots3_10-d63fff64480d/classifier.pt'
$env:MATCHPULSE_MODEL_VERSION = 'temporal-shots3_10-d63fff64480d/classifier.pt'
$env:MATCHPULSE_MATCH_COUNT = '2'
$env:MATCHPULSE_GPU_WORKERS = '1'
$env:MATCHPULSE_OFFSETS_JSON = '{"cam-1":120,"cam-2":120}'
$env:MATCHPULSE_SESSION_SECONDS = '120'
$env:MATCHPULSE_SESSION_BUDGET_USD = '0.25'
$env:MATCHPULSE_MOCK_SCORES_JSON = ''
docker compose up --build -d
```

Open <http://localhost:3000>. Startup buffers until the detector and sources are
ready, then the model scores each completed observation. Real scores do not
guarantee a visible switch: the director retains the current match unless another
healthy match beats its configured staying bonus and confirmation requirement. To
request seven sources, keep the same credentials/model and use the settings below.
The older measured capacity result belongs to the legacy model:

```powershell
$env:MATCHPULSE_MATCH_COUNT = '7'
$env:MATCHPULSE_GPU_WORKERS = '4'
$env:MATCHPULSE_SESSION_SECONDS = '120'
$env:MATCHPULSE_SESSION_BUDGET_USD = '0.75'
$env:MATCHPULSE_OFFSETS_JSON = '{"cam-1":120,"cam-2":120,"cam-3":120,"cam-4":120,"cam-5":120,"cam-6":120,"cam-7":120}'
```

## Deterministic mock switching demo

Use two matches and explicit mock scores to demonstrate a visible automatic switch:

```powershell
$env:MATCHPULSE_MONITOR = 'true'
$env:MATCHPULSE_ML_MODE = 'features_mock'
$env:MATCHPULSE_MATCH_COUNT = '2'
$env:MATCHPULSE_GPU_WORKERS = '1'
$env:MATCHPULSE_SESSION_SECONDS = '120'
$env:MATCHPULSE_SESSION_BUDGET_USD = '0.25'
$env:MATCHPULSE_MOCK_SCORES_JSON = '{"cam-1":0.1,"cam-2":0.9}'
docker compose up --build -d
```

Open the page. It holds playback in an explicit startup buffer while the detector
loads and sources open, then resumes when the worker reports readiness. The first
prediction needs five seconds of observed playback. The mock scores above choose
`cam-2` after that window; manual picks hold for 30 seconds. They are a labelled
transport/director demonstration, not model output. Removing the override still
uses the explicit mock classifier; set `MATCHPULSE_ML_MODE=real` and the installed
checkpoint path to use the selected temporal GRU.

Only backend `MATCHPULSE_MONITOR=true` enables inference. Browser messages cannot
select arbitrary source URLs or start YOLO directly. One shared session is owned
by the first connected viewer; additional viewers receive state without controlling
its clock. Closing the controlling viewer, heartbeat expiry, source EOF, the session
limit or shutdown stops the owned invocation. Long pauses release the GPU and a
resume starts a fresh observation period. Restart the backend for another session
after its time or budget limit is reached.
Explicit control/publication transport failures can recover after a five-second
delay, with a new clock epoch and observation period. Recovery attempts share the
same session allowance and stop after the configured bounded retry count.
Checkpoint, schema and model failures remain terminal until corrected.

```powershell
docker compose logs --tail 100 backend
docker compose down
```

The default session is bounded to 300 seconds and a conservative estimated $1
allowance, including reserved startup/idle overhead on each retry. Supported limits
are 10–3600 seconds and $0.01–$20 per session. Retries share the allowance. This is
an application estimate, not a provider billing cap; restarting the backend creates
a new session and allowance. The separately authorised development experiment
budget is not reset by these controls.

## Sources, offsets and access

Default sources are `match-1.mp4` through `match-7.mp4` in
`match-switcher-poc-videos`, region `eu-west-2`, with IDs `cam-1` through `cam-7`.
`MATCHPULSE_MATCH_COUNT` selects 1–7 default sources. To align different recordings,
configure source offsets explicitly:

```powershell
$env:MATCHPULSE_OFFSETS_JSON = '{"cam-1":120,"cam-2":42.5}'
```

The common replay clock is `media.currentTime - offset_seconds`; source time is
`offset_seconds + replay_position`. Matching file timestamps are not assumed to
represent matching broadcasts. The worker permit is the last actual viewer report,
not an extrapolated clock. Pauses/stalls freeze it; a seek increments the clock epoch
and discards earlier predictions/caches. No frame beyond that permission watermark
may enter a window. Startup buffering is separate from measured rolling processing
latency. There is no precomputed prediction timeline in this implementation.
If a partial EOF closed one worker connection, seeking restarts the owned group
at the new viewer position using the existing allowance. Normal active-stream
seeks keep their connections. A completely ended session requires a backend restart.

For custom source keys or authorised HTTPS URLs, replace the default registry:

```powershell
$env:MATCHPULSE_SOURCES_JSON = '[{"match_id":"cam-1","label":"Match A","key":"match-1.mp4","offset_seconds":120},{"match_id":"cam-2","label":"Match B","key":"match-2.mp4","offset_seconds":42.5}]'
```

For private S3 objects, set `MATCHPULSE_SOURCE_ACCESS=presigned`, your bucket/region,
and backend AWS credentials with read access to only the required objects. Temporary
credentials can use `AWS_SESSION_TOKEN`. `MATCHPULSE_SOURCE_URL_TTL` defaults to 3600
seconds; the backend refreshes signed URLs before expiry and the worker uses refreshed
URLs on recovery. Explicit external `source_url`/optional `playback_url` configurations
must remain valid for the session; the registry cannot renew an externally signed URL.
The browser reads the media independently and therefore receives its playable URL.

Browser WebSocket origins default to `http://localhost:3000` and
`http://127.0.0.1:3000`. Set comma-separated `MATCHPULSE_ALLOWED_ORIGINS` for other
frontend origins; wildcards, embedded credentials and URL paths are rejected. CLI
probes without an Origin header remain supported. For hosted deployment, set
`MATCHPULSE_BIND_ADDRESS` to the required interface, terminate HTTPS/WSS at your
deployment ingress, and build with the public `REACT_APP_WS_URL=wss://...` endpoint
and exact allowed frontend origin.

Control updates target four per second and latest-score reads target ten per
second, measured start to start. With the private WebSocket transport these update
bounded local caches; persistent connections carry compact messages to the workers.
The legacy Dict transport remains limited by network round-trip time. Permits stay
bounded by actual viewer reports. Probe metrics identify transport, update duration,
score age and the owned stop method. A WebSocket stop acknowledgement is distinct
from cancelling a Modal SDK invocation. The historical `owned_worker_cancelled`
probe field aliases `owned_worker_stop_confirmed`; use the transport and stop-method
fields to interpret it. Two-source real latency is measured below; larger stream
counts require their own finite validation.

## Measured legacy-model performance (historical)

The final real-GRU run passed both complete-capacity and three-second latency
gates on seven distinct configured S3 sources over 60 seconds, using four T4s
partitioned 2+2+2+1. Receipt: ignored local
`backend/ml_inference/artifacts/overhaul/probe-7-11.json`.

| Sources / GPUs | Model / transport | Delivered recommendations | Endpoint-to-WebSocket latency | Result |
|---|---|---|---|---|
| 2 / 1 T4 | Mock / Dict, historical | 10 / 10 | 1.546–2.171 s; median 1.859 s | Infrastructure only |
| 2 / 1 T4 | Real GRU / private WebSocket | 10 / 10 | 1.453–1.765 s; median 1.5465 s | Passed |
| 7 / 2 T4 | Real GRU / private WebSocket | 0 / 28 | Deadline/backlog failures | Failed |
| 7 / 4 T4, before reader priming | Real GRU / private WebSocket | 16 / 28 | Warm interval only: 1.687–2.421 s | Failed full run |
| **7 / 4 T4, final** | **Real GRU / private WebSocket** | **28 / 28, full seven-source cohorts** | **1.578–2.157 s; median 1.899 s** | **Passed; no 3 s misses** |

The final run computed **196 per-match windows** and processed **6,300 newly
sampled frames**, corresponding to the paced aggregate requirement of **105 FPS**.
It recorded zero decoder failures and zero worker deadline misses. Startup buffering
took **19.547 seconds**, separately from rolling processing latency. All seven
source watermarks reached 900 and every queue/backlog was zero after the bounded
drain. The actual maximum reader queue was 21 samples, within the 32-sample bound.
The preferred sub-second latency target was not met. A one-minute replay does not
establish full-match reliability or capacity under different media/network conditions.

Historical failures remain relevant. On two T4s, the three-source shard completed
84 windows but missed 11 processing deadlines; the four-source shard developed
backlog and lost six windows to bounded audio-history eviction. The first four-T4
attempt had four early reader errors/resets and delivered only 16/28 windows.
Its 14 late recommendations at endpoints 33–59 were not evidence of a successful
full run. Current probes require every endpoint and every registered source score;
legitimate degraded application recommendations cannot satisfy the capacity gate.

In the final run, aggregate timings across parallel workers were 106.64 s for
detector calls, 151.79 s for visual append, 40.68 s for completed-window assembly,
0.704 s for classifier calls and 0.055 s for publication; source reading totalled
53.25 s including I/O. These parallel/nested counters are not additive end-to-end
latency or an unpaced decoder benchmark. The final recorded director pass was
about 0.146 ms. Observed OMP/OpenBLAS/MKL thread limits were 4/4/4, with NumExpr 1,
despite image requests for one; no independent BLAS speedup is claimed.

Backend `latency_seconds` starts at the worker's first permission for the completed
endpoint and includes compute plus delivery. The probe's strict viewer-clock
measurement additionally captures control propagation.
`worker_completion_to_backend_seconds` isolates post-compute delivery.

## Historical correctness evidence and validation limits

The earlier legacy-audio proof at
`backend/ml_inference/artifacts/overhaul/equivalence.json` passed all six windows:
two real sources, each at `[0,5]`, `[2,7]`, `[4,9]`. Every comparison had maximum
absolute difference **0** and **0** elements outside `atol=2e-5`, `rtol=1e-5`.
This is not the selected model's required v3-audio equivalence receipt. All outputs
in that historical proof were finite float32 `(75,215)`, with equal player slots, teams,
interpolation, ball, camera and audio fields. Each source inferred 75 frames for
the first window, then only 30 new frames per overlap, reusing 45 observations.

The infrastructure handoff initially passed 442 Python tests and 40 frontend tests
plus a production build. Updated product checks and browser limits are recorded
above. Docker CLI was unavailable, so image builds and actual
`docker compose config` were not verified here; YAML/default configuration was checked locally.
The successful capacity probe uses a headless viewer clock and acknowledges
recommendations; it is not an HTML-video or visual-continuity test.
Inference cleanup observed zero running inputs and zero backlog in all owned cloud
pools. The product review frontend is CPU-only; monitoring remains opt-in.

## Local development and validation

Use Python 3.12 and Node 24. The commands below do not start cloud inference:

```powershell
$env:MATCHPULSE_MONITOR = 'false'
$env:MATCHPULSE_ALLOWED_ORIGINS = 'http://localhost:3000,http://127.0.0.1:3000'
python -m pip install -r backend/requirements.txt
python -m pip install pytest
python -B -m pytest -p no:cacheprovider backend/tests backend/ml_inference/tests -q
python -B -m backend.main
```

In a second terminal:

```powershell
Set-Location frontend/sports-streaming-service
$env:PORT = '3000'
$env:REACT_APP_WS_URL = 'ws://127.0.0.1:8000'
npm ci
npm start
```

For the reviewed native launch path, first load the private credentials and real-mode
environment variables above, then run the existing deployment environment:

```powershell
$env:MATCHPULSE_MONITOR = 'true'
$env:MATCHPULSE_ML_MODE = 'real'
& backend/ml_inference/.venv-deploy/Scripts/python.exe -B -m backend.main
```

In a second terminal, serve the preserved frontend on port 3000:

```powershell
Set-Location frontend/sports-streaming-service
$env:PORT = '3000'
$env:REACT_APP_WS_URL = 'ws://127.0.0.1:8000'
npm start
```

Use the seven-source variables above for four T4s, a 120-second monitoring limit,
a $0.75 estimated allowance and 120-second offsets for every match. This avoids
depending on unverified Docker image builds. All local test servers, including
the temporary port-3020 server, have been stopped.

Frontend checks are `npm test -- --watchAll=false --runInBand` and `npm run build`.
Backend unit/socket tests use an explicit fake cloud bridge; they do not prove GPU
readiness. A separately bounded paid source→Modal→backend→WebSocket probe is:

```powershell
# Set the explicit monitoring/mode/token variables above first.
python -B -m backend.probe_replay --allow-cloud --matches 2 --seconds 20 --startup-timeout 90 --budget 0.25
```

The probe requires both `--allow-cloud` and `MATCHPULSE_MONITOR=true`. It uses a paced
headless viewer clock, not HTML video decoding, and reports that distinction. It
drains for 3.25 seconds at the frozen final position, reports expected/missing/censored
windows, actual endpoint-to-WebSocket receipt latency, ACK delivery, deadline misses,
bounded published-watermark backlog and owned-input cleanup. Every recommendation
reports its observed source count and whether all registered sources are scored.
Capacity `passed` requires every expected endpoint, the complete source cohort at
each recommendation, and no run errors. Healthy-subset recommendations remain valid
for the application but cannot establish full-source capacity. Mock scores remain
labelled. Running this command incurs a separate bounded inference cost.

## Modal deployment and checkpoint handoff

The current procedure uses only application-local, SHA-verified inputs. The
research delivery is read-only; no SDK upload path points into the research
checkout. Place the already-authorized detector weights at
`artifacts/model-release/yolo26s.pt`. Its required SHA256 is
`646f8bc3fe0a656803d95c294f7852321748cb29d13466a1af8862e2db384a1b`.
The trusted selected export is copied to
`artifacts/model-release/temporal-shots3_10-d63fff64480d/classifier.pt`, SHA256
`d63fff64480d00835c14bc7c726e062b00278126d517e1e9eceb1abe0aafbd1e`.
These ignored artifacts are not committed or uploaded as research directories.

The packaged wheel is
`backend/ml_inference/runtime/matchpulse-0.1.0+autonomous1-py3-none-any.whl`, SHA256
`3040593a8c23338d17a2d54ac5b76eed6be7df1ed6074386207f5a6010343291`.
The exact audio decoder, release instructions, provenance and published real smoke
fixture are copied into this application. Build-time checks verify the detector,
wheel and smoke files. The checkpoint is stored separately in the immutable
inference-only model Volume, not baked into the image.

From the repository root in the authenticated deployment environment, run each
explicit step once and inspect its receipt before continuing:

```powershell
& backend/ml_inference/.venv-deploy/Scripts/python.exe -B -m backend.ml_inference.winning_model deploy --allow-cloud
& backend/ml_inference/.venv-deploy/Scripts/python.exe -B -m backend.ml_inference.winning_model install --allow-cloud
& backend/ml_inference/.venv-deploy/Scripts/python.exe -B -m backend.ml_inference.winning_model equivalence --allow-cloud
& backend/ml_inference/.venv-deploy/Scripts/python.exe -B -m backend.ml_inference.winning_model idle
& backend/ml_inference/.venv-deploy/Scripts/python.exe -B -m backend.ml_inference.winning_model probe --allow-cloud
& backend/ml_inference/.venv-deploy/Scripts/python.exe -B -m backend.ml_inference.winning_model idle
```

The `winning_model` helper uses a **new, separate $3 task ledger** at ignored
`artifacts/winning-model/budget.json`. Its reservations are $0.60 deployment,
$0.05 installation/readiness, $0.30 source equivalence and $0.70 for one seven-source,
30-second real probe with a 120-second startup allowance. Deployment and probe
subprocess deadlines are 1,200 and 210 seconds. Each invocation performs one
attempt; there are no automatic retries. Prior overhaul and product-polish ledgers
and receipts are preserved. These estimates do not impose a provider-side hard cap.

Deployment requires the existing private
`backend/ml_inference/artifacts/overhaul/ws-credentials.json` and existing
`matchpulse-inference-replay-auth` Secret. It updates only the endpoint using the
existing token; this helper creates no credentials. Tokens remain backend-only and
are neither printed nor included in model/probe receipts. Deployment output stays
in private ignored logs. A missing credential is a setup error, not permission to
create a different account or application.

Installation verifies immutable checkpoint bytes before upload, with overwrite
disabled, then invokes only the CPU `ClassifierWorker` readiness method. If the
same version already exists, explicitly use `install --verify-only --allow-cloud`;
the helper does not retry an upload automatically. Readiness verifies the selected
head, exact checkpoint/runtime sources, schema, 4,179-parameter architecture,
evaluation mode, saved normalization and the published real fixture score within
the declared absolute tolerance `2e-5` (`rtol=0`). The canonical worker runtime is
Python 3.13, NumPy 2.1.3 and Torch 2.11.0. A local noncanonical CPU smoke is useful
development evidence but does not replace this cloud readiness check.

The equivalence call uses two registered real sources at source offset 120, one
T4 and a 240-second result deadline; all six completed windows must pass the v3
audio/feature comparison. It records the owned input and cancels only that input
on failure, without terminating a container pool. Before the probe, inspect `idle`
and wait for zero runners, running inputs and backlog; it reads only inference
function statistics and never stops an application. The probe requires the
selected readiness and equivalence receipts, disables captions, and acknowledges
recommendations using a paced headless viewer. It tests neither browser media nor
paid transcription. Uncertain worker stops retain the full reservation; settlement
requires the backend's confirmed `worker_stop_succeeded` result.

Current canonical/new-model cloud success and browser acceptance are pending
until their actual receipts are recorded; the commands above are a procedure,
not evidence that those checks passed.

The app is `matchpulse-inference`; model storage is `matchpulse-inference-models`
and compact session state uses `matchpulse-inference-replay`. GPU containers scale
to zero after active inputs end. Deployment and validation never need to modify the
separate research repository or its `matchpulse-private` application.

### Original GRU rollback and its historical evidence

The previous trusted full-audio GRU's 249,677-byte export remains installed in the
inference-only Volume as `gru-stage1-02de8309/classifier.pt`, SHA256
`02de83095e5eaaf2f22978e89eec8515633ecd680ba0e9834cfb46d8cbea9319`.
Its CPU readiness was reverified on the deployed autonomous runtime without
overwriting the checkpoint. Older real-stream measurements elsewhere in this
README remain historical baseline evidence.
`backend.demo --allow-cloud --matches 7 --seconds 120 --model
legacy` is the explicit runtime rollback. It uses its own original audio contract;
the new model's corrected channels are not silently applied to legacy serving.

To recheck the existing rollback checkpoint after a deployment, copy its verified
bytes into `artifacts/model-release/gru-stage1-02de8309/classifier.pt`, then run:

```powershell
& backend/ml_inference/.venv-deploy/Scripts/python.exe -B -m backend.ml_inference.winning_model install --model legacy --verify-only --allow-cloud
```

Rollback readiness retains the original full 215-input/64-hidden GRU audit and
saved training-only `masked-channel-zscore-v1` normalization. Training-only
`best.pt`, 210-channel bundles and arbitrary version aliases are incompatible.
Both versions fail explicitly rather than falling back.

Changing the active model does not require an image deployment: the current
worker has both audited loaders. If the worker deployment needs recovery, run
the inference-only `winning_model deploy --allow-cloud` command above, verify
legacy readiness, and launch with `--model legacy`. The original runtime wheel
is retained at `backend/ml_inference/runtime/matchpulse-0.1.0-py3-none-any.whl`;
the autonomous wheel retains its validated legacy API. Do not replace an existing
Volume path, force an upload, or delete either model. Active identity is available
in backend session messages and the frontend monitoring tooltip.

The legacy model observes five seconds and targets labelled events 3–10 seconds ahead
(`matchpulse-anticipation-v1.0.0`). It was trained on four official training matches
(20,628 windows) and selected on two validation matches (10,326 windows), with no
held-out test access. Saved `masked-channel-zscore-v1` normalization was fitted
only on training data and retains all 215 channels, including the five audio fields.
Research training used a one-second decision grid; this app evaluates every two
seconds without changing the five-second input representation.

Predictive discrimination is weak: validation average precision **0.051729** versus
positive prevalence **0.051133**, ROC AUC **0.476397**. At a validation-fitted 20%
clip-union footage budget, event recall was 21/80 (26.25%), precision 0.060606 and
window recall 0.075758, with about 127 false-alert episodes per match-hour.
Those research forwarding metrics are not measured multi-match director quality.
Scores are uncalibrated. The baseline remains preferred to its clipped comparison;
neither supports a claim of reliable event anticipation.

The [ML package notes](backend/ml_inference/README.md) describe the current streaming
contracts, worker limits, validation tools and the retained legacy API.

## Platform expansion files

Expansion work includes the files below; `git status` is authoritative as live-caption
verification evolves. An external commit (`fd00d69`) recorded the previous overhaul
during this task; the implementation agents did not issue a commit, push or branch
change. Existing work was preserved.

### Modified expansion files

```text
README.md
backend/Dockerfile
backend/demo.py
backend/main.py
backend/replay/session.py
backend/replay/sources.py
docker-compose.yml
frontend/Dockerfile
frontend/sports-streaming-service/src/App.js
frontend/sports-streaming-service/src/App.test.js
frontend/sports-streaming-service/src/components/MainPlayer.js
frontend/sports-streaming-service/src/components/VideoTile.js
frontend/sports-streaming-service/src/feeds.js
```

### New expansion files

```text
.dockerignore
.env.example
backend/captions/__init__.py
backend/captions/__main__.py
backend/captions/audio.py
backend/captions/live_process.py
backend/captions/pipeline.py
backend/captions/provider.py
backend/captions/realtime.py
backend/captions/schema.py
backend/captions/service.py
backend/captions/stream_audio.py
backend/football_platform/__init__.py
backend/football_platform/catalog.py
backend/football_platform/providers.py
backend/football_platform/server.py
backend/football_platform/service.py
backend/local_config.py
backend/match_metadata.py
backend/requirements-captions.txt
backend/tests/conftest.py
backend/tests/test_captions.py
backend/tests/test_caption_realtime.py
backend/tests/test_caption_stream_audio.py
backend/tests/test_caption_early_events.py
backend/tests/test_caption_adapter_lifecycle.py
backend/tests/test_live_caption_session.py
backend/tests/test_local_config.py
backend/tests/test_match_metadata.py
backend/tests/test_platform.py
backend/tests/test_platform_app.py
frontend/sports-streaming-service/src/Platform.css
frontend/sports-streaming-service/src/captions.js
frontend/sports-streaming-service/src/components/CommentaryCaptions.js
frontend/sports-streaming-service/src/components/DataNotice.js
frontend/sports-streaming-service/src/components/NewsPage.js
frontend/sports-streaming-service/src/components/ReplayScore.js
frontend/sports-streaming-service/src/components/TablesPage.js
frontend/sports-streaming-service/src/data/matches.json
frontend/sports-streaming-service/src/leagueSearch.js
frontend/sports-streaming-service/src/liveCaptions.js
frontend/sports-streaming-service/src/liveCaptions.test.js
frontend/sports-streaming-service/src/platform.test.js
frontend/sports-streaming-service/src/platformApi.js
frontend/sports-streaming-service/src/useLiveCaptions.js
frontend/sports-streaming-service/src/useSourcePlayback.js
```

### UI redesign files

The redesign additionally updates `public/index.html`, `public/manifest.json`,
`src/App.css`, `src/index.css`, `src/components/DirectorPanel.js`, `src/director.js`
and the existing platform/caption components and tests listed above. It adds
`public/fonts/inter-variable.woff2`, its `OFL.txt` licence and provenance
`README.txt`, plus `src/redesign.test.js`. The obsolete frontend components
`src/components/HowItWorks.js` and `src/components/SessionMoments.js` are deleted.
All paths in this paragraph are relative to `frontend/sports-streaming-service/`.

## Director/UI handoff manifest (historical)


Historical snapshot from the previous handoff, rather than current Git status: 25 modified,
43 new and 2 deleted application files, including the preserved infrastructure
overhaul and subsequent director/UI work. Ignored cloud receipts, credentials,
virtual environments and media are not part of this manifest. The research
repository was kept read-only; no branch switch, commit or push was performed.

### Modified

```text
.gitignore
README.md
backend/Dockerfile
backend/main.py
backend/ml_inference/README.md
backend/ml_inference/classifiers.py
backend/ml_inference/modal_app.py
backend/ml_inference/modal_client.py
backend/ml_inference/tests/test_classifiers.py
backend/ml_inference/tests/test_modal_client.py
backend/ml_inference/tests/test_worker_definition.py
backend/requirements.txt
backend/websocket_manager.py
docker-compose.yml
frontend/Dockerfile
frontend/sports-streaming-service/public/index.html
frontend/sports-streaming-service/public/manifest.json
frontend/sports-streaming-service/src/App.css
frontend/sports-streaming-service/src/App.js
frontend/sports-streaming-service/src/App.test.js
frontend/sports-streaming-service/src/components/MainPlayer.js
frontend/sports-streaming-service/src/components/VideoTile.js
frontend/sports-streaming-service/src/feeds.js
frontend/sports-streaming-service/src/setupTests.js
frontend/sports-streaming-service/src/useBackendSocket.js
```

### New

```text
backend/.dockerignore
backend/demo.py
backend/ml_inference/incremental.py
backend/ml_inference/install_checkpoint.py
backend/ml_inference/overhaul_browser.py
backend/ml_inference/overhaul_cloud.py
backend/ml_inference/replay_asgi.py
backend/ml_inference/replay_client.py
backend/ml_inference/replay_contract.py
backend/ml_inference/replay_media.py
backend/ml_inference/replay_metrics.py
backend/ml_inference/replay_runner.py
backend/ml_inference/replay_state.py
backend/ml_inference/replay_validation.py
backend/ml_inference/replay_ws_client.py
backend/ml_inference/tests/test_incremental.py
backend/ml_inference/tests/test_install_checkpoint.py
backend/ml_inference/tests/test_replay_asgi.py
backend/ml_inference/tests/test_replay_client.py
backend/ml_inference/tests/test_replay_media.py
backend/ml_inference/tests/test_replay_metrics.py
backend/ml_inference/tests/test_replay_runner.py
backend/ml_inference/tests/test_replay_state.py
backend/ml_inference/tests/test_replay_ws_client.py
backend/ml_inference/tests/test_replay_ws_integration.py
backend/probe_replay.py
backend/replay/__init__.py
backend/replay/director.py
backend/replay/session.py
backend/replay/sources.py
backend/tests/test_demo.py
backend/tests/test_director_policy.py
backend/tests/test_replay.py
backend/tests/test_websocket_shutdown.py
frontend/sports-streaming-service/public/touchline.svg
frontend/sports-streaming-service/src/components/DirectorPanel.js
frontend/sports-streaming-service/src/components/HowItWorks.js
frontend/sports-streaming-service/src/components/SessionMoments.js
frontend/sports-streaming-service/src/director.js
frontend/sports-streaming-service/src/director.test.js
frontend/sports-streaming-service/src/replayProtocol.js
frontend/sports-streaming-service/src/replayProtocol.test.js
frontend/sports-streaming-service/src/useBackendSocket.test.js
```

### Deleted

```text
backend/video_ingester.py
backend/video_processor.py
```

These deleted modules were the obsolete backend RGB-array ingester and unfinished
processor. The active CPU backend does not import them.
