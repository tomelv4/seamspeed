# RevenueCat — integrated (2026-11-16)
This file is supposed to serve as a memory to you if you have to interact with user's RevenueCat account via integration proxy at any later point in time.

## Identifiers (from /setup response)
- rc_project_id: proj2a19e29b
- apple_app_id: app4c1fdeef97
- play_app_id: app8e82b5e6ae
- entitlement_lookup_key: pro
- offering_lookup_key: default
- Packages:
  - $rc_monthly -> prod912e3e1823 ($9.99 / P1M, trial: none)
  - $rc_annual  -> prod5cc1ae63b1 ($59.99 / P1Y, trial: none — updated via /products)
- Dashboard: https://app.revenuecat.com/projects/proj2a19e29b
- App identity: Purchases.logIn(device_id) (no auth in app; device_id from local storage is the backend user id)

## Status check
curl -sS -H "$AUTH" "$INTEGRATION_PROXY_URL/internal/revenuecat/projects/1c2003c0-f5a0-4a0e-93ff-c2eba84f6382/status"
If project_state is earlier than project_created, re-fetch the RevenueCat playbook via integration expert.

## Later updates (integration proxy APIs ONLY — never the RevenueCat REST API)
- Upsert price/package: POST $INTEGRATION_PROXY_URL/internal/revenuecat/projects/1c2003c0-f5a0-4a0e-93ff-c2eba84f6382/products
  body: {"products":[{"package":"$rc_monthly","price":9.99,"currency":"USD","period":"P1M","prices":[{"amount_micros":9990000,"currency":"USD"}]}]}
- Remove package: DELETE .../products/%24rc_monthly
- Recover identifiers / keys: re-run idempotent /setup

## Taking purchases LIVE (user does these)
1. Upload App Store Connect in-app purchase key / API key (.p8) and Google Play service-account JSON in the RevenueCat dashboard.
2. Set up payment profiles in App Store Connect and Play Console.
3. Create matching subscription products with the SAME product IDs shown in RevenueCat.
4. Release build → TestFlight / Play internal testing → submit for review.
All steps are in the FAQ section of the payments panel.
