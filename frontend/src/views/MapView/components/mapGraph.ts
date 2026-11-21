import type { ElementDefinition, Position } from 'cytoscape'
import type { MapData, MapNode, MapRelation } from '@/api/mapAPI'

type Axis = 'x' | 'y'
type Direction = { axis: Axis; before: string; after: string }
type MapArea = { locations: MapNode[]; elements: ElementDefinition[] }

const cardinal: Partial<Record<MapRelation, { axis: Axis; sourceFirst: boolean }>> = {
  north_of: { axis: 'y', sourceFirst: true },
  south_of: { axis: 'y', sourceFirst: false },
  west_of: { axis: 'x', sourceFirst: true },
  east_of: { axis: 'x', sourceFirst: false },
}

// A topological pass assigns display ranks that satisfy every direction on one axis.
// If the pass cannot visit the whole group, the directions on that axis conflict.
function rankLocations(locations: MapNode[], directions: Set<Direction>, axis: Axis) {
  const slots = new Map(
    locations.map(({ id }) => [id, { rank: 0, incoming: 0, next: [] as string[] }]),
  )
  for (const { axis: directionAxis, before, after } of directions) {
    if (directionAxis !== axis) continue
    slots.get(before)!.next.push(after)
    slots.get(after)!.incoming++
  }

  const ready = locations.filter(({ id }) => slots.get(id)!.incoming === 0).map(({ id }) => id)
  for (const id of ready) {
    const { rank, next } = slots.get(id)!
    for (const nextId of next) {
      const neighbor = slots.get(nextId)!
      neighbor.rank = Math.max(neighbor.rank, rank + 1)
      if (--neighbor.incoming === 0) ready.push(nextId)
    }
  }

  return ready.length === locations.length ? slots : null
}

function placeLocations(locations: MapNode[], directions: Set<Direction>) {
  const xRanks = rankLocations(locations, directions, 'x')
  const yRanks = rankLocations(locations, directions, 'y')
  if (!xRanks || !yRanks) return null

  const columns = new Map<number, Map<number, string[]>>()
  for (const { id } of locations) {
    const x = xRanks.get(id)!.rank
    const y = yRanks.get(id)!.rank
    if (!columns.has(x)) columns.set(x, new Map())
    const rows = columns.get(x)!
    if (!rows.has(y)) rows.set(y, [])
    rows.get(y)!.push(id)
  }

  // Separate markers in the same slot without reversing any explicit ordering.
  // These are canvas offsets for legibility and have no in-world scale.
  const positions = new Map<string, Position>()
  let left = 0
  for (const [, rows] of [...columns].sort(([a], [b]) => a - b)) {
    const width = Math.max(...Array.from(rows.values(), (ids) => ids.length))
    for (const [y, ids] of rows) {
      ids.forEach((id, index) => {
        positions.set(id, { x: left + (index + (width - ids.length) / 2) * 164, y: y * 124 })
      })
    }
    left += width * 164
  }
  return positions
}

export function buildMapLayout(data: MapData) {
  const nodes = new Map(data.nodes.map((node) => [node.id, node]))
  const incident = new Map(data.nodes.map(({ id }) => [id, [] as Direction[]]))
  for (const { source, target, relation } of data.edges) {
    const rule = cardinal[relation]
    if (!rule || source === target || !nodes.has(source) || !nodes.has(target)) continue
    const direction = {
      axis: rule.axis,
      before: rule.sourceFirst ? source : target,
      after: rule.sourceFirst ? target : source,
    }
    incident.get(source)!.push(direction)
    incident.get(target)!.push(direction)
  }

  const visited = new Set<string>()
  const areaByLocation = new Map<string, number>()
  const areas: MapArea[] = []
  let hasConflictingDirections = false
  // Each connected set of directions gets its own canvas view. The API gives
  // no bearings between these sets, even when travel connects two of them.
  for (const { id } of data.nodes) {
    if (visited.has(id) || !incident.get(id)?.length) continue
    const group = new Set([id])
    const directions = new Set<Direction>()
    for (const current of group) {
      visited.add(current)
      for (const direction of incident.get(current)!) {
        directions.add(direction)
        group.add(direction.before === current ? direction.after : direction.before)
      }
    }

    const locations = Array.from(group, (id) => nodes.get(id)!)
    const positions = placeLocations(locations, directions)
    if (!positions) {
      hasConflictingDirections = true
      continue
    }
    const elements: ElementDefinition[] = locations.map((node) => ({
      group: 'nodes',
      data: { ...node, label: node.name },
      position: positions.get(node.id)!,
    }))
    for (const { id } of locations) areaByLocation.set(id, areas.length)
    areas.push({ locations, elements })
  }

  for (const edge of data.edges) {
    const area = areaByLocation.get(edge.source)
    if (
      edge.relation === 'travelled_to' &&
      edge.source !== edge.target &&
      area !== undefined &&
      area === areaByLocation.get(edge.target)
    ) {
      areas[area]!.elements.push({ group: 'edges', data: { ...edge } })
    }
  }

  return {
    areas,
    areaByLocation,
    unplaced: data.nodes.filter(({ id }) => !areaByLocation.has(id)),
    hasConflictingDirections,
  }
}

/** Elapsed session time, including hours beyond 24; never a wall-clock Date. */
export function formatSessionTime(seconds: number): string {
  const elapsed = Math.floor(seconds)
  const hours = Math.floor(elapsed / 3600)
  const minutes = Math.floor((elapsed % 3600) / 60)
  const remainder = elapsed % 60
  return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${remainder.toString().padStart(2, '0')}`
}
