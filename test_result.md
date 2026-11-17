#====================================================================================================
# START - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================

# THIS SECTION CONTAINS CRITICAL TESTING INSTRUCTIONS FOR BOTH AGENTS
# BOTH MAIN_AGENT AND TESTING_AGENT MUST PRESERVE THIS ENTIRE BLOCK

# Communication Protocol:
# If the `testing_agent` is available, main agent should delegate all testing tasks to it.
#
# You have access to a file called `test_result.md`. This file contains the complete testing state
# and history, and is the primary means of communication between main and the testing agent.
#
# Main and testing agents must follow this exact format to maintain testing data. 
# The testing data must be entered in yaml format Below is the data structure:
# 
## user_problem_statement: {problem_statement}
## backend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.py"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## frontend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.js"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## metadata:
##   created_by: "main_agent"
##   version: "1.0"
##   test_sequence: 0
##   run_ui: false
##
## test_plan:
##   current_focus:
##     - "Task name 1"
##     - "Task name 2"
##   stuck_tasks:
##     - "Task name with persistent issues"
##   test_all: false
##   test_priority: "high_first"  # or "sequential" or "stuck_first"
##
## agent_communication:
##     -agent: "main"  # or "testing" or "user"
##     -message: "Communication message between agents"

# Protocol Guidelines for Main agent
#
# 1. Update Test Result File Before Testing:
#    - Main agent must always update the `test_result.md` file before calling the testing agent
#    - Add implementation details to the status_history
#    - Set `needs_retesting` to true for tasks that need testing
#    - Update the `test_plan` section to guide testing priorities
#    - Add a message to `agent_communication` explaining what you've done
#
# 2. Incorporate User Feedback:
#    - When a user provides feedback that something is or isn't working, add this information to the relevant task's status_history
#    - Update the working status based on user feedback
#    - If a user reports an issue with a task that was marked as working, increment the stuck_count
#    - Whenever user reports issue in the app, if we have testing agent and task_result.md file so find the appropriate task for that and append in status_history of that task to contain the user concern and problem as well 
#
# 3. Track Stuck Tasks:
#    - Monitor which tasks have high stuck_count values or where you are fixing same issue again and again, analyze that when you read task_result.md
#    - For persistent issues, use websearch tool to find solutions
#    - Pay special attention to tasks in the stuck_tasks list
#    - When you fix an issue with a stuck task, don't reset the stuck_count until the testing agent confirms it's working
#
# 4. Provide Context to Testing Agent:
#    - When calling the testing agent, provide clear instructions about:
#      - Which tasks need testing (reference the test_plan)
#      - Any authentication details or configuration needed
#      - Specific test scenarios to focus on
#      - Any known issues or edge cases to verify
#
# 5. Call the testing agent with specific instructions referring to test_result.md
#
# IMPORTANT: Main agent must ALWAYS update test_result.md BEFORE calling the testing agent, as it relies on this file to understand what to test next.

#====================================================================================================
# END - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================



#====================================================================================================
# Testing Data - Main Agent and testing sub agent both should log testing data below this section
#====================================================================================================
## Iteration 6 context (main agent)
- Step timing sync: backend/biomech.py detects take_off/BFC/FFC/release from tracked skeleton (ankle landings, highest bowling wrist), each of 27 steps snapped into a window relative to those events, monotonic order. Measured values per step (knee angles, stride % height, release height %, elbow extension est, approach speed est) stored in step.metrics. analysis.events saved.
- Prompt: critical coach, judge vs ideal ranges supplied by user (STEPS now have when + ideal; step.ideal shown in StepCard as IDEAL box).
- Pose sampling 30fps.


## Iteration 7 context (main agent)
- Backend pose quality: extract_pose now reports frame coverage, critical-joint coverage and mean confidence for shoulders, elbows, wrists, hips, knees and ankles. Rating is a transparent capture-quality heuristic, not a calibrated probability.
- Measurement gating: Track.knee, Track.joint and Track.trunk_lean reject low-confidence keypoints; ankle contact heuristic now uses a clip-wide ground reference and requires sustained near-ground frames.
- Event provenance: event methods and keypoint confidence are persisted. The wrist's highest point is explicitly a wrist-apex proxy, not confirmed ball release. AI and typical-gap estimates are distinguished.
- Measurement scope: removed uncalibrated approach-speed and 2D elbow-extension/legality proxies; renamed wrist height at apex and trunk lean metrics to make their 2D estimate nature explicit.
- Timestamp integrity: sync_times no longer manufactures timestamps from template event anchors; AI timestamps are preserved when pose anchors cannot safely constrain a step, otherwise unavailable times remain null.
- AI guardrails: prompt now forbids invented numeric measurements, uncalibrated pace estimates, 2D elbow legality claims and injury predictions from a single visual proxy.
- Frontend: report now displays pose quality and wrist-apex release limitation; step metric panel identifies values as 2D pose estimates.
- CI: added .github/workflows/paced-backend-checks.yml to compile backend and run focused biomechanics unit tests on the feature branch / PR.
- Retesting required: all changes above are pending automated execution. Do not mark working=true until the workflow passes.


## Iteration 7 test update
- First GitHub Actions run (PR #1, run 44086941159): backend compilation passed; biomechanics unit tests failed (7 failures, 22 passed).
- Failures were test/contract mismatches: one confidence fixture lowered the wrong knee keypoint; release-proxy timestamps were being asserted as confirmed release; the template-anchor test did not distinguish an AI-estimated release from template-generated BFC/FFC/take-off; event-method wording assertion needs verification against the updated event payload.
- Corrective test changes committed; rerun required. Do not mark these tasks working until a clean run.


## Iteration 7 retest note
- Follow-up changes: preserve original 30/60 fps capture sampling up to 900 frames; interpolated pose frames are explicitly low-confidence and excluded from biomechanics; capture-quality coverage counts observed frames only; body-scale estimate requires confident keypoints; foot contact requires a visible swing before ground contact.
- Corrected a test fixture to lower the actual front-knee keypoint and aligned timestamp assertions with the rule that wrist apex is not a confirmed release.
- CI rerun pending after these commits.


## Iteration 7 CI checkpoint
- GitHub Actions run 44087518569: backend compile passed and 29/29 biomechanics unit tests passed in 0.10s on the commit tested by that run.
- Subsequent commits added 60fps sampling, stricter observed-vs-interpolated confidence handling, qualitative coaching references, evidence-level metadata, pace/injury guardrails, and frontend UI/type changes. These later commits still require a fresh CI run.
- Frontend TypeScript validation has now been added to the workflow.


## Iteration 7 CI checkpoint 2
- GitHub Actions run 44088422794 on the current feature-branch snapshot: backend compile passed and 29/29 biomechanics tests passed in 0.20s.
- Frontend typecheck did not start because the repository has no committed yarn.lock; setup-node's Yarn cache path therefore failed. Workflow corrected to install from the exact package.json versions without lockfile caching. Frontend typecheck remains pending.


## Iteration 7 follow-on work
- Real progress reporting: backend analysis records stage/percent/message updates; the Analyze screen now polls and displays those actual stages instead of a 40-second timer that advanced regardless of work.
- Frontend typecheck exposed a pre-existing React Native 0.88 typing incompatibility in frontend/src/theme.ts (StyleSheet.NamedStyles no longer exported); makeStyles typing was updated to a compatible generic.
- Validation tooling added on the feature branch: manual event annotation schema, event timing evaluator, and unit tests. CI now includes those evaluator tests.
- Repository safety correction: three validation files were briefly created on main because the branch argument was omitted from a file-creation call. They were immediately deleted from main and recreated on the feature branch. The files are confirmed absent from main. GitHub retains the add/delete commits in main's history; no app code or configuration was left changed there.
- Full backend and frontend CI rerun required after these latest changes.


## Iteration 7 CI checkpoint 3
- GitHub Actions run 44089428450: backend compile passed and 33/33 tests passed, including the new event-validation evaluator.
- Frontend dependency install passed. TypeScript then reported widespread RN 0.88 style-prop widening errors across existing screens; the shared makeStyles helper has been updated to restore contextual ViewStyle/TextStyle/ImageStyle inference. A fresh typecheck is required.
- Added camera-view classification and only exposes 2D sagittal-plane metrics when Gemini reports a high-confidence side-on camera view. Other views retain visual coaching feedback without misleading side-plane measurements.
- Increased pose sampling capacity to cover 20-second clips at up to 60fps.


## Iteration 7 CI checkpoint 4
- Backend test suite: 33/33 passing on the latest tested snapshot (run 44089428450); backend compile also passed.
- Frontend typecheck identified that the shared style helper needed stronger contextual typing; the helper was adjusted again to preserve React Native style literal types. Retest pending.
- Actual progress reporting is now wired from backend stages through API polling into the Analyze screen; the previous timer-driven fake progress sequence has been removed.
- Added camera-view classification confidence. Side-plane measurements are only exposed for high-confidence side-on footage; other views are limited to visual assessment.
- Hardened report assembly: invalid statuses are downgraded to not_visible, scores are finite and clamped, and raw AI timestamps are only accepted when there are no event anchors and the time is in-clip and monotonic.
- Added 20-second/60fps pose capacity and interpolated frames are excluded from measured confidence.
