# Geographic Map

The campaign map uses the existing `MapData` contract and has a sample demo with fictional locations and evidence.

## Modes and states

- `/map` loads session data with GET `/map`. It never generates automatically.
- **Generate Map** sends one bodyless POST `/map/generate`. Loading/generating disable API actions and the mode switch; overlapping requests are prevented.
- Missing APIs, network errors, and unsupported responses show an explicit error with **Retry loading**. They never trigger a sample fallback.
- `{ "nodes": [], "edges": [], "source_segment_count": 0 }` shows the empty state.
- **Show sample demo** switches to `/map?demo=sample`. Opening this URL directly skips the initial map request. The page labels the data as invented, disables generation, and makes no map API calls in sample mode.
- **Use session data** removes the demo query parameter and loads the backend map again. The fixture never enters the map store or API client.
- **Back to session** returns to `/home`. The existing login guard applies in both modes.

The demo needs no **map** backend. Manual use still requires the player/session backend for login and route authentication. The automated browser regression mocks that authentication check as well as map responses.

## Map and details

`components/MapGraph.vue` accepts a `data: MapData` prop. `components/mapGraph.ts` builds the display layout without modifying the input.

- Explicit north, south, east, and west relationships set the relative order of markers on parchment. Independent sets of directions are shown in separate map areas. The layout uses screen spacing for legibility and has no distance scale.
- **Unplaced locations** includes locations that lack usable cardinal directions and groups with conflicting directions.
- Completed travel appears as a dotted path when both endpoints are placed in the same area. Every relationship remains selectable from the relationship list, including travel involving unplaced locations or different areas and relationships with missing endpoints.
- Scroll, pinch, or use the zoom buttons to zoom. Drag the background or use the arrow keys while the canvas is focused to pan. **Fit to View** fits the active area.
- Canvas selections highlight the marker or path and update the corresponding list button. Locations show mention counts, first and last seen times, and evidence and timestamps from their relationships. Relationships show the endpoints, relation, evidence, and timestamp.
- Timestamps use elapsed session seconds formatted as `HH:MM:SS`, including hours beyond 24.
- **Clear selection**, a background tap, or Escape while focus is within the component deselects.
- The lists remain available for keyboard selection and when the canvas cannot render. Evidence is rendered as text.

The component rebuilds Cytoscape when the displayed area or data changes, refits on resize, and destroys the renderer and observer on unmount. Changing data modes resets selection.

## API contract

`src/api/mapAPI.ts` validates the fields used by the map.

Both GET and POST return a direct `MapData` JSON object synchronously; there is no response envelope or job polling. POST has no body or session ID and uses the backend's current session.

| Object | Fields |
| --- | --- |
| MapData | `nodes: MapNode[]`, `edges: MapEdge[]`, `source_segment_count: number` |
| MapNode | `id: string`, `name: string`, `mentions: number`, `first_seen: number`, `last_seen: number` |
| MapEdge | `id: string`, `source: string`, `target: string`, `relation: MapRelation`, `evidence: string`, `timestamp: number` |

Counts are nonnegative integers. Timestamps are finite, nonnegative numeric seconds relative to the session. IDs and source/target references are strings; evidence is plain text.

Supported relation values:

```text
north_of, south_of, east_of, west_of, near,
inside, contains, connected_to, travelled_to
```

Empty arrays and a zero count represent an empty stored map. HTTP 404 is reported as API unavailable. Requests use the backend address selected in the session.

## Automated checks

Run from `frontend/`:

```sh
npm ci
npm run type-check
npm run build
npm run test:unit -- --run src/views/MapView
npx eslint src/views/MapView e2e/map.spec.ts

npx playwright install chromium --only-shell
npm run test:e2e -- e2e/map.spec.ts --project=chromium --reporter=list
```

Vitest covers the API and store, cardinal placement, contradictory and missing directions, travel filtering, selection and evidence, keyboard panning, resize and cleanup, and sample/session switching. Component tests use headless Cytoscape. Playwright exercises the canvas at desktop and mobile widths with mocked authentication and map API responses.

## Manual checks

1. From `frontend/`, run `npm ci` and `npm run dev`. Join a session through the existing login flow.
2. Open `http://localhost:5173/map?demo=sample`. Confirm the invented-data label, counts, and disabled **Generate Map** button. In DevTools Network, confirm there are no backend `/map` or `/map/generate` requests; the player existence check is expected.
3. Select **Willowbrook** in the graph or location list. Confirm 3 mentions, first seen `00:00:10`, and last seen `00:02:00`.
4. Select **Silverwood Forest north of Willowbrook** in the relationship list. Confirm the evidence and timestamp `00:00:30`. Select the dotted path between these locations to see the completed journey and timestamp `00:02:00`.
5. Select **Old Watchtower** under **Unplaced locations**. Confirm it appears in the list and its evidence is available in the selection panel.
6. Test zoom, pan, and **Fit to View**. Tab to a list button, press Enter or Space to select, then press Escape to deselect.
7. Resize to 390px wide. Confirm the map, details, and lists stack vertically and fit the page.
8. Choose **Use session data** and confirm a GET request. Click **Generate Map** and confirm one bodyless POST. Switch back to sample mode and confirm the selection is cleared.
