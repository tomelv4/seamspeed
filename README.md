# PACED

**Understand Every Movement.**

PACED is a fast-bowling video analysis and coaching app. It combines pose tracking, movement-by-movement feedback, interactive video review, training drills and workload logging.

## Product principles

- **Evidence before scores.** A movement is marked unassessable when the relevant joints, event or footage are not clear enough.
- **Transparent measurements.** Pose-derived angles are 2D camera-plane estimates, not 3D biomechanics or force measurements.
- **No invented pace.** Bowling speed is unavailable unless a calibrated radar or ball-tracking source is connected.
- **No video injury diagnosis.** Video observations describe visible technique only. Workload indicators describe logged training volume and recovery trends; neither predicts an injury.
- **Protect the original app.** Development work happens on feature branches. Do not merge or deploy without explicit approval.

## Architecture

- `frontend/`: Expo / React Native application using Expo Router.
- `backend/`: FastAPI service, MongoDB persistence, video processing and analysis endpoints.
- `backend/pose.py`: RTMPose-based person tracking and COCO-17 pose extraction.
- `backend/biomech.py`: event heuristics, confidence-gated 2D measurements and step timing.
- `backend/analysis_contract.py`: defensive parsing and normalisation of multimodal AI responses.
- `backend/validation_metrics.py`: event-timing evaluation against manual annotations.
- `docs/VALIDATION_DATASET.md`: consent, annotation format and real-video validation protocol.

## Analysis limitations

- Side-on footage is the preferred view for camera-plane measurements. Rear, front-on and oblique views are not interchangeable with side-on footage.
- Back-foot and front-foot contact are ankle-ground heuristics, not force-plate measurements.
- The wrist's highest point is only a proxy. It is not proof of ball release.
- Release timing is accepted as an AI visual estimate only when ball separation is explicitly reported as visible; this is not sensor confirmation.
- Synthetic pose tests verify code behaviour, not real-world tracking accuracy.

## Checks

Run the automated backend checks from the repository root:

```bash
python -m pip install numpy pytest pytest-xdist opencv-python-headless
pytest -c backend/pytest.ini -n 0 backend/tests/test_biomech_unit.py backend/tests/test_validation_metrics.py backend/tests/test_analysis_contract.py
python -m compileall -q backend
```

Type-check the frontend:

```bash
cd frontend
yarn install
yarn tsc --noEmit
```

## Real-video validation

Do not describe event detection or pose measurements as validated until they have been evaluated against consented, manually annotated bowling footage. Follow the protocol in [docs/VALIDATION_DATASET.md](docs/VALIDATION_DATASET.md). Report results separately by event, camera view and source frame rate.
