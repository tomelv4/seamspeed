# PaceSensei — PRD

## Original problem
"Build a mobile app: a fast bowling analysis app like swingsensei is for golf but for pace bowling in cricket." Follow-up: "Add the ChatGPT AI Models integration to my app."

## User choices
- AI video analysis (Gemini 3 Flash `gemini-3-flash-preview`, Emergent LLM key)
- Session history + progress charts, personalized drills, pace band + injury-risk / mixed action indicators
- No accounts: one profile per device (X-Device-Id header, device_id in local storage)
- Dark, athletic, premium style
- ChatGPT (OpenAI `gpt-5.5`) AI Coach chat with streaming (SSE)

## Architecture
- Backend: FastAPI + MongoDB (profiles, analyses, coach_messages). Video is stored in a temp file only long enough for Gemini to analyse it, then deleted. Drills library is static and lives in the code.
- Frontend: Expo Router. Tabs are Home / Analyze / Drills / Progress (native tabs on iOS 26+). Stack screens: report/[id], drill/[id], coach, profile (modal).

## Implemented (2026-06)
- Record or upload a clip, get a Gemini report: overall score, 6 phase scores, faults with fixes, strengths, tips, pace band gauge, injury risk / mixed action
- Session history, delete report, progress stats and charts (score/pace/phases), recurring faults
- 12-drill library with phase filters and a "For You" filter based on the latest faults
- AI Coach chat (GPT-5.5, streaming, saved history, knows the latest 3 reports)
- Bowler profile (name, arm, style, level) used in the AI prompts
- Testing: backend 16/16 pass; frontend iteration 1 passed. Fixed afterwards: profile form reset, PressScale tap area, native-tabs import path, chip touch size, top pace stat, clear-chat error handling

## Implemented — iteration 2 (2026-11)
- 27-step fast-bowling biomechanics breakdown (Gemini timestamps, score, status, observation, cue per step)
- Server-side body tracking (rtmlib RTMPose ONNX, 12 fps) → stick-figure skeleton over the replay (react-native-svg), timeline step markers, slow-mo, step jump, measured joint angles (front/back knee, bowling elbow, trunk lean)
- Videos stored in Emergent Object Storage, streamed with Range support
- Live ball-by-ball coaching session: camera (expo-camera) or upload → Gemini watches → GPT-5.5 coach speech → OpenAI TTS (gpt-4o-mini-tts, onyx) via expo-audio; session summary
- RevenueCat paywall (Emergent managed): 1 free bowling analysis; drills, progress, coach chat, live sessions and further analyses need Pro. Monthly $9.99; yearly requested $59.99 (Test Store still shows $79.99, see revenuecat.md)

## Implemented — iteration 3 (2026-11)
- Rebrand to PACED: racing-green / charcoal / off-white / silver identity, Sora + Manrope + JetBrains Mono, square-mark wordmark, refined section ticks, squarer buttons
- Side-by-side Compare screen (/compare): pick 2 deliveries, step-synced skeleton players, score/angle deltas, 27-step table (Pro)
- Pro Action Overlay: dashed silver elite reference-model skeleton (template per step, anchored to the bowler's hips and torso length, mirrored for direction/arm) toggled on the report player
- 7-day trial requested on yearly plan via the RevenueCat proxy (Test Store still shows $79.99)

## Implemented — iteration 4 (2026-11)
- Workload tracker (/workload, Pro): manual ball logs + live-session balls auto-counted; 7-day acute, 4-week chronic, A:C ratio (after 21 days of history), weekly spike, consecutive days, rest days, age-band weekly guide; status low/caution/high
- Injury Scanner on reports: lumbar spine, side strain, front-leg overload, shoulder/rotator cuff, hamstring/groin (Gemini from the video) + workload spikes (from logged volume)
- Profile age band (Under 16 / 16-18 / 19-22 / 23+)
- Full structured live sessions: GPT-5.5 plan → warm-up checklist with timers → technique drills → bowling block → skills test → cool-down; spoken stage transitions (/api/speak); achievements + test result + tips in the summary

## Backlog
- P1: Store videos (Emergent Object Storage) and play the clip back inside the report
- P1: Side-by-side compare of two deliveries
- P2: Share report card image, pro-action reference library, premium subscription

## Update (Jun 2026)
- Full analysis uses Gemini 3.1 Pro (gemini-3.1-pro-preview); ball-by-ball live coaching stays on Gemini 3 Flash for speed.
- Pose: RTMPose-x + YOLOX-x ("performance" mode, env POSE_MODE), 24 fps, 960px, multi-person tracking, picks the bowler (most mobile/large/confident track), stitches broken tracks, fills gaps of up to 4 frames, smooths jitter only. The measured angle timeline is sent to Gemini before it writes the analysis.
- PACED logo: app icon/adaptive/splash/favicon + in-app wordmark (assets/images/paced-*.png).
- Dev-only "Unlock Pro for testing" switch in Profile (__DEV__ only); device ID shown for RevenueCat promotional grants.
- Prices come from the store/RevenueCat products (no hardcoded USD). AUD is set in App Store Connect / Play Console / RevenueCat test store.
- Analyses run asynchronously: POST /api/analyses returns {id,status:processing}; the client polls GET /api/analyses/{id}. Analyses still processing at startup are marked failed. Fixes the 502 proxy timeout.
- 27-step timing sync (backend/biomech.py): take-off/BFC/FFC/release detected from the skeleton; each step snapped into its window relative to those events; measured per-step values are only used when the event was really measured; trunk lean is signed (forward/back). Each step carries `ideal` (user-supplied ranges), shown in the step card. The Gemini prompt is now critical and judges every step against those ideals.
