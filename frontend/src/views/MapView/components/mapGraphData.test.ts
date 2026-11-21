import { describe, expect, it } from 'vitest'
import type { MapEdge, MapNode } from '@/api/mapAPI'
import { mapSample } from '@/fixtures/mapSample'
import { buildMapLayout, formatSessionTime } from './mapGraph'

describe('directional map layout', () => {
  it('honors all four directions and draws only completed travel between placed locations', () => {
    const original = structuredClone(mapSample)
    const { areas, unplaced } = buildMapLayout(mapSample)
    expect(areas).toHaveLength(1)
    expect(unplaced.map(({ id }) => id)).toEqual(['sample-tower'])
    const { elements } = areas[0]!
    const positions = new Map(elements.map(({ data, position }) => [data.id, position]))
    const village = positions.get('sample-village')!
    const forest = positions.get('sample-forest')!
    const crossing = positions.get('sample-crossing')!
    const abbey = positions.get('sample-abbey')!
    expect(forest.y).toBeLessThan(village.y)
    expect(crossing.x).toBeLessThan(village.x)
    expect(crossing.y).toBeGreaterThan(forest.y)
    expect(abbey.x).toBeGreaterThan(forest.x)
    expect(abbey.y).toBeGreaterThan(village.y)
    expect(elements.filter(({ group }) => group === 'edges')).toEqual(
      mapSample.edges
        .filter(({ relation }) => relation === 'travelled_to')
        .map((edge) => ({ group: 'edges', data: edge })),
    )
    expect(mapSample).toEqual(original)
  })

  function layout(ids: string[], links: [string, MapEdge['relation'], string][]) {
    const nodes: MapNode[] = ids.map((id) => ({
      id,
      name: id,
      mentions: 1,
      first_seen: 0,
      last_seen: 0,
    }))
    const edges: MapEdge[] = links.map(([source, relation, target], index) => ({
      id: String(index),
      source,
      relation,
      target,
      evidence: '',
      timestamp: 0,
    }))
    return buildMapLayout({ nodes, edges, source_segment_count: 0 })
  }

  it('keeps independent directional areas apart even when travel joins them', () => {
    const { areas, unplaced } = layout(
      ['a', 'b', 'c', 'd', 'e', 'f'],
      [
        ['a', 'north_of', 'b'],
        ['c', 'east_of', 'd'],
        ['a', 'travelled_to', 'c'],
        ['b', 'travelled_to', 'e'],
        ['e', 'near', 'd'],
        ['e', 'inside', 'f'],
        ['f', 'connected_to', 'd'],
        ['f', 'east_of', 'missing'],
      ],
    )
    expect(areas.map(({ locations }) => locations.map(({ id }) => id))).toEqual([
      ['a', 'b'],
      ['c', 'd'],
    ])
    expect(areas.flatMap(({ elements }) => elements).every(({ group }) => group === 'nodes')).toBe(
      true,
    )
    expect(unplaced.map(({ id }) => id)).toEqual(['e', 'f'])
  })

  it('keeps contradictory groups unplaced while laying out consistent directions', () => {
    const { areas, unplaced, hasConflictingDirections } = layout(
      ['a', 'b', 'c', 'd', 'e', 'f'],
      [
        ['a', 'north_of', 'b'],
        ['b', 'north_of', 'c'],
        ['a', 'south_of', 'c'],
        ['d', 'west_of', 'e'],
        ['e', 'east_of', 'd'],
        ['f', 'south_of', 'f'],
      ],
    )
    expect(hasConflictingDirections).toBe(true)
    expect(unplaced.map(({ id }) => id)).toEqual(['a', 'b', 'c', 'f'])
    expect(areas.map(({ locations }) => locations.map(({ id }) => id))).toEqual([['d', 'e']])
  })

  it('separates markers sharing a rank without changing explicitly ordered axes', () => {
    const { areas } = layout(
      ['a', 'b', 'c', 'd'],
      [
        ['a', 'north_of', 'b'],
        ['a', 'north_of', 'c'],
        ['b', 'west_of', 'd'],
        ['c', 'west_of', 'd'],
      ],
    )
    const positions = new Map(areas[0]!.elements.map(({ data, position }) => [data.id, position]))
    expect(positions.get('b')!.x).not.toBe(positions.get('c')!.x)
    for (const id of ['b', 'c']) {
      expect(positions.get(id)!.y).toBeGreaterThan(positions.get('a')!.y)
      expect(positions.get(id)!.x).toBeLessThan(positions.get('d')!.x)
    }
  })

  it('handles empty maps and travel-only maps without claiming any positions', () => {
    expect(layout([], []).areas).toEqual([])
    const { areas, unplaced } = layout(['a', 'b'], [['a', 'travelled_to', 'b']])
    expect(areas).toEqual([])
    expect(unplaced.map(({ id }) => id)).toEqual(['a', 'b'])
  })
})

describe('session-relative timestamps', () => {
  it.each([
    [0, '00:00:00'],
    [90.9, '00:01:30'],
    [3661, '01:01:01'],
    [90000, '25:00:00'],
  ])('formats %s seconds as %s without wrapping at midnight', (seconds, expected) => {
    expect(formatSessionTime(Number(seconds))).toBe(expected)
  })
})
