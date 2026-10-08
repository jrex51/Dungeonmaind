# Geographic map manual checks

Run `npm ci` and `npm run dev` from `frontend/`. Join a session through the
existing login flow, then click **Geographic Map** alongside **Timeline**.

- `/map` loads with GET `/map`. It never generates automatically. A missing map
  API displays an error with **Retry loading** and **Show sample demo**.
- **Generate Map** sends one bodyless POST `/map/generate`. Loading and generating
  disable API actions and the mode switch; repeated clicks do not overlap requests.
- A response `{ "nodes": [], "edges": [], "source_segment_count": 0 }` shows the
  empty state. A populated response shows counts, locations, and relationships;
  graph visualization is intentionally deferred.
- **Show sample demo** switches to `/map?demo=sample`. Open this URL directly to
  skip the initial map request. The page prominently labels invented sample data,
  disables generation, and makes no map API calls in this mode. **Use session
  data** removes the query parameter and loads the backend map again.
- **Back to session** returns to `/home`. An unauthenticated `/map` visit follows
  the same login guard as `/timeline`, including in demo mode.

The demo needs no **map** backend, but the existing player/session backend must
still be available for login and route authentication. Demo mode does not bypass
authentication. The fixture is `src/fixtures/mapSample.ts` and never enters the
API store or backend.

## Provisional API contract

Issues #46 and #49 specify fields and endpoints, but not field types, timestamp
units, response envelopes, or generation request payloads. `src/api/mapAPI.ts`
isolates the following assumptions and validates incoming data:

- GET and POST return a direct `MapData` JSON object, synchronously; no job polling.
- IDs and edge source/target references are strings; evidence is a string.
- `mentions` and `source_segment_count` are nonnegative integer counts.
- `first_seen`, `last_seen`, and `timestamp` are nonnegative numeric seconds
  relative to the session, consistent with timeline timestamps.
- Relations use the nine values proposed in #46.
- POST has no body or session ID and uses the backend's current session.
- No stored map is represented by empty arrays and a zero count. HTTP 404 is
  reported as API unavailable until the backend specifies different semantics.

Unsupported response formats produce an explicit error, never sample fallback.
Adapt the API boundary after the backend contract is finalized.
