# PACED real-video validation dataset

## Why this exists

Synthetic skeletons test code paths; they do not prove that pose tracking or event detection works on a real bowling action. This dataset is the acceptance gate for the biomechanics engine. Do not claim validated accuracy until results are measured on manually labelled moving footage.

## Clip collection

Build a consented, de-identified set of single-delivery clips. For the first validation round aim for:
- At least 20 deliveries from at least 10 different bowlers.
- Right- and left-arm bowlers.
- Side-on, rear, oblique and front-on recordings, labelled honestly.
- A mix of club and higher-level bowlers, run-up styles and body shapes.
- Original source frame rate retained where available (30, 60, 120 or 240 fps).
- Full bowler visible from run-up through follow-through; record when the bowler or ball leaves frame.

Do not use names, faces or identifying details in annotation IDs. Obtain permission before storing or sharing footage.

## Annotation format

One JSON file per clip:

```json
{
  "clip_id": "clip_001",
  "bowling_arm": "right",
  "camera_view": "side_on",
  "fps": 120,
  "events": {
    "take_off": 2.14,
    "bfc": 2.39,
    "ffc": 2.66,
    "release": 2.79
  },
  "tolerances": {
    "take_off": 0.06,
    "bfc": 0.05,
    "ffc": 0.05,
    "release": 0.04
  },
  "notes": "Ball separation visible; full body remains in frame."
}
```

Times are seconds from the start of the clip. Use null or omit an event when it genuinely cannot be labelled. Do not substitute wrist apex for ball release.

## Event labelling rules

- **Take-off:** first frame the relevant take-off foot clearly leaves the ground into the bound.
- **BFC:** first frame the back foot makes ground contact.
- **FFC:** first frame the front foot makes ground contact in the delivery stride.
- **Release:** first frame the ball is visibly separated from the fingers. If the ball is occluded or indistinguishable, mark release unlabelled and explain why.
- When the exact frame is ambiguous, have two reviewers label independently and adjudicate disagreements; keep the adjudicated time and note the uncertainty.

## Run the evaluator

Export the tracked pose result as JSON and pair it with the manual annotation:

```bash
python backend/validation_metrics.py --pose pose.json --annotation annotation.json
```

The report gives event misses, absolute timing error and the proportion within the configured tolerance. Report results separately by event, source FPS and camera view. Never pool all camera angles into one headline accuracy figure.

## Acceptance gates

1. Verify the detector on side-on clips first, with both bowling arms represented.
2. Publish per-event mean/median absolute error, miss rate and within-tolerance rate.
3. Inspect false positives and missed events manually; a high average can hide a failure on one event type.
4. Validate rear/oblique/front-on views separately before enabling those measurements.
5. Keep release timing explicitly marked as a wrist-apex proxy until ball-separation detection has been validated against manual release labels.
6. Do not restore pace estimates, 3D rotation claims or injury-risk predictions from 2D footage based on these event tests; they require their own calibrated validation.
