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

## Backlog
- P1: Store videos (Emergent Object Storage) and play the clip back inside the report
- P1: Side-by-side compare of two deliveries
- P2: Share report card image, pro-action reference library, premium subscription
