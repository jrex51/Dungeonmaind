<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import cytoscape, { type Core } from 'cytoscape'
import type { MapData, MapEdge } from '@/api/mapAPI'
import { buildMapLayout, formatSessionTime } from './mapGraph'

type Selection = { kind: 'node' | 'edge'; id: string }

const props = defineProps<{ data: MapData }>()
const container = ref<HTMLDivElement | null>(null)
const detailsPanel = ref<HTMLElement | null>(null)
const selection = ref<Selection | null>(null)
const areaIndex = ref(0)
const renderError = ref(false)
let graph: Core | undefined
let observer: ResizeObserver | undefined

const mapLayout = computed(() => buildMapLayout(props.data))
const activeArea = computed(() => mapLayout.value.areas[areaIndex.value])
const locationSections = computed(() =>
  [
    { title: 'Unplaced locations', locations: mapLayout.value.unplaced },
    {
      title: 'Mapped locations',
      locations: props.data.nodes.filter(({ id }) => mapLayout.value.areaByLocation.has(id)),
    },
  ].filter(({ locations }) => locations.length),
)
const selectedNode = computed(() =>
  selection.value?.kind === 'node'
    ? props.data.nodes.find((node) => node.id === selection.value?.id)
    : undefined,
)
const selectedEdge = computed(() =>
  selection.value?.kind === 'edge'
    ? props.data.edges.find((edge) => edge.id === selection.value?.id)
    : undefined,
)
const relatedEdges = computed(() => {
  const id = selectedNode.value?.id
  return props.data.edges.filter((edge) => edge.source === id || edge.target === id)
})
const names = computed(() => new Map(props.data.nodes.map(({ id, name }) => [id, name])))
const hasMissingEndpoints = computed(() =>
  props.data.edges.some(
    ({ source, target }) => !names.value.has(source) || !names.value.has(target),
  ),
)

function relationshipName(edge: MapEdge): string {
  const source = names.value.get(edge.source) ?? edge.source
  const target = names.value.get(edge.target) ?? edge.target
  return `${source} ${edge.relation.replace(/_/g, ' ')} ${target}`
}

function clearSelection(): void {
  selection.value = null
}

function select(kind: Selection['kind'], id: string): void {
  const { areaByLocation } = mapLayout.value
  if (kind === 'node') {
    areaIndex.value = areaByLocation.get(id) ?? areaIndex.value
  } else {
    const edge = props.data.edges.find((item) => item.id === id)
    if (edge?.relation === 'travelled_to') {
      const area = areaByLocation.get(edge.source)
      if (area !== undefined && area === areaByLocation.get(edge.target)) areaIndex.value = area
    }
  }
  selection.value = { kind, id }
}

function revealDetails(): void {
  void nextTick(() => detailsPanel.value?.scrollIntoView?.({ block: 'nearest' }))
}

function selectFromIndex(kind: Selection['kind'], id: string, event: MouseEvent): void {
  select(kind, id)
  if (event.detail > 0) revealDetails()
}

function clearDetails(): void {
  clearSelection()
  detailsPanel.value?.focus({ preventScroll: true })
}

function highlightSelection(): void {
  graph?.elements('.highlighted').removeClass('highlighted')
  if (selection.value) graph?.getElementById(selection.value.id).addClass('highlighted')
}

function fit(): void {
  if (!graph) return
  graph.resize()
  graph.fit(undefined, graph.width() < 440 ? 30 : 60)
}

function zoom(factor: number): void {
  if (!graph) return
  graph.zoom({
    level: graph.zoom() * factor,
    renderedPosition: { x: graph.width() / 2, y: graph.height() / 2 },
  })
}

function panWithKeyboard(event: KeyboardEvent): void {
  const offsets: Record<string, { x: number; y: number }> = {
    ArrowUp: { x: 0, y: 42 },
    ArrowDown: { x: 0, y: -42 },
    ArrowLeft: { x: 42, y: 0 },
    ArrowRight: { x: -42, y: 0 },
  }
  const offset = offsets[event.key]
  if (!offset || !graph) return
  event.preventDefault()
  graph.panBy(offset)
}

function destroyGraph(): void {
  observer?.disconnect()
  observer = undefined
  graph?.destroy()
  graph = undefined
}

function renderGraph(): void {
  destroyGraph()
  renderError.value = false
  if (!container.value || !activeArea.value) return

  try {
    graph = cytoscape({
      container: container.value,
      elements: activeArea.value.elements,
      layout: { name: 'preset', fit: false },
      autoungrabify: true,
      autounselectify: true,
      boxSelectionEnabled: false,
      minZoom: 0.1,
      maxZoom: 2.5,
      style: [
        {
          selector: 'node',
          style: {
            label: 'data(label)',
            shape: 'diamond',
            width: 19,
            height: 19,
            'background-color': '#783426',
            'border-width': 2.5,
            'border-color': '#fae9be',
            color: '#422918',
            'font-family': 'Georgia, serif',
            'font-weight': 'bold',
            'font-size': 15,
            'text-valign': 'bottom',
            'text-halign': 'center',
            'text-margin-y': 6,
            'text-wrap': 'ellipsis',
            'text-max-width': '150px',
            'text-outline-color': '#f5e4b7',
            'text-outline-width': 1.5,
          },
        },
        {
          selector: 'edge',
          style: {
            width: 2.6,
            'line-color': '#7c4933',
            // Short, rounded dashes leave a readable gap between dots.
            'line-style': 'dashed',
            'line-dash-pattern': [1, 8],
            'line-cap': 'round',
            'curve-style': 'bezier',
            'control-point-step-size': 38,
            'overlay-padding': 8,
          },
        },
        {
          selector: 'node.highlighted',
          style: { 'background-color': '#4a5938', 'border-color': '#423021', 'border-width': 3 },
        },
        {
          selector: 'edge.highlighted',
          style: { 'line-color': '#4a5938', width: 4 },
        },
      ],
    })
    graph.on('tap', (event) => {
      if (event.target === graph) {
        clearSelection()
        return
      }
      select(event.target.isNode() ? 'node' : 'edge', event.target.id())
      const heading = detailsPanel.value?.getBoundingClientRect().top
      if (event.originalEvent && heading !== undefined && heading >= window.innerHeight) {
        revealDetails()
      }
    })
    highlightSelection()
    fit()
    if (typeof ResizeObserver !== 'undefined') {
      observer = new ResizeObserver(fit)
      observer.observe(container.value)
    }
  } catch {
    destroyGraph()
    renderError.value = true
  }
}

onMounted(renderGraph)
watch(
  () => props.data,
  () => {
    areaIndex.value = 0
    clearSelection()
  },
  { deep: true },
)
watch(activeArea, renderGraph, { flush: 'post' })
watch(selection, highlightSelection)
onBeforeUnmount(destroyGraph)
</script>

<template>
  <div class="map-graph" @keydown.esc="clearSelection">
    <div class="graph-layout">
      <div class="map-sheet">
        <div class="graph-toolbar">
          <label v-if="mapLayout.areas.length > 1" class="area-picker">
            Map area
            <select v-model.number="areaIndex" @change="clearSelection">
              <option v-for="(area, index) in mapLayout.areas" :key="index" :value="index">
                {{ area.locations[0]?.name }} area
              </option>
            </select>
          </label>
          <div
            v-if="activeArea && !renderError"
            class="view-controls"
            aria-label="Map controls"
            role="group"
          >
            <button type="button" aria-label="Zoom out" @click="zoom(0.8)">−</button>
            <button type="button" aria-label="Zoom in" @click="zoom(1.25)">+</button>
            <button type="button" @click="fit">Fit to View</button>
          </div>
        </div>

        <div class="map-field">
          <div
            v-show="activeArea && !renderError"
            ref="container"
            class="graph-canvas"
            role="region"
            tabindex="0"
            aria-label="Campaign map. Use arrow keys to pan. Choose locations and relationships from the lists."
            @keydown="panWithKeyboard"
          ></div>
          <div v-if="activeArea && !renderError" class="compass" aria-hidden="true">
            <b>N</b><span>W</span><i>✦</i><span>E</span><span>S</span>
          </div>
          <p v-if="renderError" class="map-message" role="alert">
            The map could not be drawn. Explore the locations and relationships below.
          </p>
          <p v-else-if="!activeArea" class="map-message" role="status">
            {{
              data.nodes.length
                ? 'No locations have enough directional evidence to place on the map.'
                : 'No locations to display.'
            }}
          </p>
        </div>

        <div v-if="activeArea && !renderError" class="map-legend">
          <span><i class="legend-route" aria-hidden="true"></i> Completed travel</span>
          <span>Relative directions · Distances unknown</span>
        </div>
      </div>

      <section
        ref="detailsPanel"
        class="details-panel"
        aria-label="Selection details"
        aria-live="polite"
        tabindex="0"
      >
        <div class="details-heading">
          <h3>
            {{
              selectedNode?.name ??
              (selectedEdge ? relationshipName(selectedEdge) : 'Selection details')
            }}
          </h3>
          <button v-if="selection" type="button" @click="clearDetails">Clear selection</button>
        </div>
        <template v-if="selectedNode">
          <dl class="location-times" aria-label="Mentions and elapsed session times">
            <div>
              <dt>Mentions</dt>
              <dd>{{ selectedNode.mentions }}</dd>
            </div>
            <div>
              <dt>First seen</dt>
              <dd>{{ formatSessionTime(selectedNode.first_seen) }}</dd>
            </div>
            <div>
              <dt>Last seen</dt>
              <dd>{{ formatSessionTime(selectedNode.last_seen) }}</dd>
            </div>
          </dl>
          <h4>Related evidence</h4>
          <ul v-if="relatedEdges.length" class="evidence-list">
            <li v-for="edge in relatedEdges" :key="edge.id">
              <div class="evidence-heading">
                <strong>{{ relationshipName(edge) }}</strong>
                <span>{{ formatSessionTime(edge.timestamp) }}</span>
              </div>
              <p class="quote">{{ edge.evidence || 'No transcript excerpt available.' }}</p>
            </li>
          </ul>
          <p v-else>No related evidence recorded.</p>
        </template>
        <template v-else-if="selectedEdge">
          <p class="edge-time">Session elapsed · {{ formatSessionTime(selectedEdge.timestamp) }}</p>
          <h4>Evidence</h4>
          <p class="quote">{{ selectedEdge.evidence || 'No transcript excerpt available.' }}</p>
        </template>
        <p v-else>Select a location or relationship to read its evidence and session timestamps.</p>
      </section>
    </div>

    <div class="map-index">
      <section
        v-for="{ title, locations } in locationSections"
        :key="title"
        class="index-section"
        :aria-label="title"
      >
        <h3>{{ title }}</h3>
        <p v-if="title === 'Unplaced locations'">
          {{
            mapLayout.hasConflictingDirections
              ? 'These locations have missing or conflicting directional evidence.'
              : 'These locations have no recorded cardinal direction.'
          }}
        </p>
        <ul class="index-list">
          <li v-for="node in locations" :key="node.id">
            <button
              type="button"
              :aria-pressed="selection?.kind === 'node' && selection.id === node.id"
              @click="selectFromIndex('node', node.id, $event)"
            >
              {{ node.name }}
            </button>
          </li>
        </ul>
      </section>

      <section class="index-section relationship-index" aria-label="Relationships">
        <h3>Relationships</h3>
        <p v-if="hasMissingEndpoints" role="status">
          Some relationships refer to locations missing from the map data.
        </p>
        <ul v-if="data.edges.length" class="index-list">
          <li v-for="edge in data.edges" :key="edge.id">
            <button
              type="button"
              :aria-pressed="selection?.kind === 'edge' && selection.id === edge.id"
              @click="selectFromIndex('edge', edge.id, $event)"
            >
              {{ relationshipName(edge) }}
            </button>
          </li>
        </ul>
        <p v-else>No geographic relationships found.</p>
      </section>
    </div>
  </div>
</template>

<style scoped>
.map-graph {
  --ink: #422918;
  --rule: #ad8150;
  --paper: #f6e8c8;
  color: var(--ink);
}

.graph-layout {
  display: grid;
  grid-template-columns: minmax(0, 2.2fr) minmax(240px, 1fr);
  align-items: start;
  gap: 1rem;
}

.map-sheet {
  min-width: 0;
  padding: 0.65rem;
  border: 1px solid #977043;
  border-radius: 6px;
  background:
    radial-gradient(ellipse at 26% 22%, #ffedc3 0%, transparent 63%),
    radial-gradient(ellipse at 80% 67%, #c88e514d 0%, transparent 64%), #efd6a3;
  box-shadow:
    inset 0 0 26px #6a3b2250,
    0 2px 5px #56391e26;
}

.graph-toolbar,
.view-controls,
.map-legend {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.4rem;
}

.graph-toolbar:empty {
  display: none;
}

.graph-toolbar {
  justify-content: space-between;
  margin-bottom: 0.6rem;
}

.area-picker {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  max-width: 100%;
  gap: 0.4rem;
  font:
    bold 0.85rem Georgia,
    serif;
}

.area-picker select {
  min-width: 0;
  max-width: 100%;
}

.map-field {
  position: relative;
  border: 1px solid var(--rule);
  outline: 1px solid #ad815065;
  outline-offset: 3px;
  background:
    repeating-linear-gradient(31deg, #6a3b2208 0 1px, transparent 1px 5px),
    radial-gradient(ellipse at 54% 42%, #f9e8bb 12%, #f0d7a2 65%, #dcb780);
  box-shadow: inset 0 0 24px #8c572642;
}

.graph-canvas {
  position: relative;
  overflow: hidden;
  height: clamp(340px, 55vh, 550px);
  cursor: grab;
}

.graph-canvas:active {
  cursor: grabbing;
}

.compass {
  position: absolute;
  top: 0.75rem;
  right: 0.75rem;
  display: grid;
  grid-template-columns: repeat(3, auto);
  place-items: center;
  gap: 0.1rem;
  color: #70452c;
  font:
    0.7rem Georgia,
    serif;
  line-height: 1;
  pointer-events: none;
}

.compass b,
.compass span:last-child {
  grid-column: 2;
}

.compass span:nth-child(2) {
  grid-column: 1;
}

.compass i {
  font-size: 1.7rem;
  font-style: normal;
}

.map-legend {
  justify-content: space-between;
  padding: 0.6rem 0.2rem 0.1rem;
  font-size: 0.82rem;
}

.legend-route {
  display: inline-block;
  width: 1.35rem;
  vertical-align: middle;
  border-top: 3px dotted #7c4933;
}

.map-message {
  padding: 1.5rem;
  text-align: center;
}

.details-panel,
.index-section {
  min-width: 0;
  padding: 1rem;
  border: 1px solid var(--rule);
  border-radius: 6px;
  background: var(--paper);
  overflow-wrap: anywhere;
}

.details-panel {
  max-height: clamp(16rem, 48vh, 28rem);
  overflow: auto;
}

.details-heading {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  align-items: start;
  gap: 0.5rem;
}

h3,
h4 {
  margin: 0;
  font-family: Georgia, serif;
}

h3 {
  font-size: 1.22rem;
}

p {
  margin: 0.5rem 0 0;
  line-height: 1.45;
}

.location-times {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem 1rem;
  margin: 0.75rem 0 1rem;
}

.location-times dt,
.edge-time,
.evidence-heading {
  font-size: 0.85rem;
}

.location-times dd {
  margin: 0.15rem 0 0;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.edge-time {
  margin-bottom: 0.85rem;
}

.evidence-list,
.index-list {
  list-style: none;
  margin: 0.65rem 0 0;
  padding: 0;
}

.evidence-list li {
  padding: 0.55rem 0;
  border-top: 1px solid #ad815066;
}

.evidence-heading {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 0.25rem 0.6rem;
}

.quote {
  padding-left: 0.6rem;
  border-left: 2px solid var(--rule);
  white-space: pre-wrap;
}

.map-index {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 1rem;
  margin-top: 1rem;
}

.relationship-index {
  grid-column: 1 / -1;
}

.index-list {
  display: flex;
  flex-wrap: wrap;
  gap: 0.45rem;
}

.index-list li {
  min-width: 0;
  max-width: 100%;
}

button,
select {
  box-sizing: border-box;
  max-width: 100%;
  min-height: 2.75rem;
  padding: 0.25rem 0.65rem;
  border: 1px solid #946b42;
  border-radius: 5px;
  color: var(--ink);
  background: #fff3d8;
  font: inherit;
  font-size: 0.875rem;
}

button {
  cursor: pointer;
  text-align: left;
  overflow-wrap: anywhere;
}

.view-controls button {
  min-width: 2.75rem;
  text-align: center;
}

button:hover {
  background: #f0d5a4;
}

button[aria-pressed='true'] {
  color: #fff3d8;
  background: #68402c;
}

button:focus-visible,
select:focus-visible,
.details-panel:focus-visible,
.graph-canvas:focus-visible {
  outline: 3px solid #783426;
  outline-offset: 2px;
}

@media (max-width: 760px) {
  .graph-layout,
  .map-index {
    grid-template-columns: minmax(0, 1fr);
  }
  .graph-canvas {
    height: clamp(275px, 40vh, 420px);
  }
}
</style>
