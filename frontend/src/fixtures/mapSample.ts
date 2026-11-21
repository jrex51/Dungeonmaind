import type { MapData } from '@/api/mapAPI'

// SAMPLE ONLY: invented places and evidence, never extracted session results.
// Read separately by the view; never stored or sent to the API.
export const mapSample: MapData = {
  nodes: [
    { id: 'sample-village', name: 'Willowbrook', mentions: 3, first_seen: 10, last_seen: 120 },
    { id: 'sample-forest', name: 'Silverwood Forest', mentions: 4, first_seen: 30, last_seen: 180 },
    { id: 'sample-tower', name: 'Old Watchtower', mentions: 1, first_seen: 90, last_seen: 90 },
    {
      id: 'sample-crossing',
      name: 'Emberford',
      mentions: 3,
      first_seen: 10,
      last_seen: 45,
    },
    { id: 'sample-abbey', name: 'Moonfall Abbey', mentions: 3, first_seen: 66, last_seen: 180 },
  ],
  edges: [
    {
      id: 'sample-north',
      source: 'sample-forest',
      target: 'sample-village',
      relation: 'north_of',
      evidence: 'Sample: Silverwood Forest lies north of Willowbrook.',
      timestamp: 30,
    },
    {
      id: 'sample-inside',
      source: 'sample-tower',
      target: 'sample-forest',
      relation: 'inside',
      evidence: 'Sample: The old watchtower stands inside Silverwood Forest.',
      timestamp: 90,
    },
    {
      id: 'sample-travel',
      source: 'sample-village',
      target: 'sample-forest',
      relation: 'travelled_to',
      evidence: 'Sample: The party travelled from Willowbrook to the forest.',
      timestamp: 120,
    },
    {
      id: 'sample-crossing-travel',
      source: 'sample-crossing',
      target: 'sample-village',
      relation: 'travelled_to',
      evidence: 'Sample: We rode from Emberford to Willowbrook.',
      timestamp: 10,
    },
    {
      id: 'sample-crossing-west',
      source: 'sample-crossing',
      target: 'sample-village',
      relation: 'west_of',
      evidence: 'Sample: Emberford is west of Willowbrook.',
      timestamp: 40,
    },
    {
      id: 'sample-crossing-south',
      source: 'sample-crossing',
      target: 'sample-forest',
      relation: 'south_of',
      evidence: 'Sample: The crossing is south of Silverwood Forest.',
      timestamp: 45,
    },
    {
      id: 'sample-abbey-east',
      source: 'sample-abbey',
      target: 'sample-forest',
      relation: 'east_of',
      evidence: 'Sample: Moonfall Abbey lies east of Silverwood Forest.',
      timestamp: 66,
    },
    {
      id: 'sample-abbey-south',
      source: 'sample-abbey',
      target: 'sample-village',
      relation: 'south_of',
      evidence: 'Sample: The abbey is south of Willowbrook.',
      timestamp: 75,
    },
    {
      id: 'sample-abbey-travel',
      source: 'sample-forest',
      target: 'sample-abbey',
      relation: 'travelled_to',
      evidence: 'Sample: We left Silverwood Forest and reached Moonfall Abbey at dusk.',
      timestamp: 180,
    },
  ],
  source_segment_count: 9,
}
