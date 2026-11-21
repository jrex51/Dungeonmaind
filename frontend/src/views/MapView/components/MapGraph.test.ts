import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, mount } from '@vue/test-utils'
import type { Core } from 'cytoscape'
import { reactive } from 'vue'
import { mapSample } from '@/fixtures/mapSample'
import MapGraph from './MapGraph.vue'

// Real Cytoscape events and selection; jsdom has no canvas renderer.
const { instances } = vi.hoisted(() => ({ instances: [] as Core[] }))
vi.mock('cytoscape', async (importOriginal) => {
  const { default: cytoscape } = await importOriginal<{ default: typeof import('cytoscape') }>()
  return {
    default: (options: import('cytoscape').CytoscapeOptions) => {
      const graph = cytoscape({
        ...options,
        container: undefined,
        headless: true,
        styleEnabled: true,
      })
      instances.push(graph)
      return graph
    },
  }
})

enableAutoUnmount(afterEach)
const disconnect = vi.fn()
let resize: () => void
beforeEach(() => {
  instances.length = 0
  disconnect.mockClear()
  vi.stubGlobal(
    'ResizeObserver',
    class {
      constructor(callback: () => void) {
        resize = callback
      }
      observe = vi.fn()
      disconnect = disconnect
    },
  )
})
afterEach(() => vi.unstubAllGlobals())

describe('MapGraph', () => {
  it('synchronizes marker and dotted route taps with evidence, timestamps and keyboard buttons', async () => {
    const wrapper = mount(MapGraph, { props: { data: mapSample } })
    const graph = instances[0]!
    expect(graph.getElementById('sample-village').style('shape')).toBe('diamond')
    const route = graph.getElementById('sample-travel')
    expect(route.style('line-dash-pattern')).toBe('1 8')
    expect(route.style('line-cap')).toBe('round')
    expect(route.style('target-arrow-shape')).toBe('none')
    expect(graph.getElementById('sample-north')).toHaveLength(0)
    graph.getElementById('sample-village').emit('tap')
    await wrapper.vm.$nextTick()
    const details = () => wrapper.get('[aria-label="Selection details"]').text()
    expect(details()).toContain('Willowbrook')
    expect(details()).toContain('Mentions3')
    expect(details()).toContain('00:00:10')
    expect(details()).toContain('00:02:00')
    expect(details()).toContain(mapSample.edges[0]!.evidence)
    expect(details()).toContain('00:00:30')
    expect(wrapper.get('[aria-pressed="true"]').text()).toContain('Willowbrook')
    route.emit('tap')
    await wrapper.vm.$nextTick()
    expect(route.hasClass('highlighted')).toBe(true)
    expect(graph.getElementById('sample-village').hasClass('highlighted')).toBe(false)
    expect(details()).toContain('Willowbrook travelled to Silverwood Forest')
    expect(details()).toContain(mapSample.edges[2]!.evidence)
    expect(details()).toContain('00:02:00')
    graph.emit('tap')
    await wrapper.vm.$nextTick()
    expect(details()).toContain('Select a location')
    const edgeButton = wrapper
      .findAll('li button')
      .find((button) => button.text().includes('north of'))!
    await edgeButton.trigger('click')
    expect(details()).toContain('Silverwood Forest north of Willowbrook')
    expect(details()).toContain(mapSample.edges[0]!.evidence)
    await wrapper.trigger('keydown', { key: 'Escape' })
    expect(graph.elements('.highlighted')).toHaveLength(0)
    expect(details()).toContain('Select a location')
  })

  it('zooms and pans with keyboard controls, fits on request and resize, and destroys stale areas', async () => {
    const wrapper = mount(MapGraph, { props: { data: structuredClone(mapSample) } })
    const graph = instances[0]!
    graph.zoom(1)
    await wrapper.get('[aria-label="Zoom in"]').trigger('click')
    expect(graph.zoom()).toBeCloseTo(1.25)
    await wrapper.get('[aria-label="Zoom out"]').trigger('click')
    expect(graph.zoom()).toBeCloseTo(1)
    const { y } = graph.pan()
    await wrapper.get('.graph-canvas').trigger('keydown', { key: 'ArrowUp' })
    expect(graph.pan().y).toBeCloseTo(y + 42)

    const fit = vi.spyOn(graph, 'fit')
    const resized = vi.spyOn(graph, 'resize')
    await wrapper.get('.view-controls button:last-child').trigger('click')
    expect(fit).toHaveBeenCalled()
    resize()
    expect(resized).toHaveBeenCalledTimes(2)
    graph.getElementById('sample-village').emit('tap')
    await wrapper.setProps({
      data: {
        nodes: [
          { id: 'real', name: 'Session place', mentions: 1, first_seen: 3601, last_seen: 3661 },
        ],
        edges: [],
        source_segment_count: 1,
      },
    })
    expect(graph.destroyed()).toBe(true)
    expect(disconnect).toHaveBeenCalledTimes(1)
    expect(wrapper.text()).not.toContain('Willowbrook')
    expect(wrapper.get('[aria-label="Selection details"]').text()).toContain('Select a location')
    expect(wrapper.get('[aria-label="Unplaced locations"]').text()).toContain('Session place')
    expect(instances).toHaveLength(1)

    await wrapper.setProps({ data: mapSample })
    const current = instances[1]!
    wrapper.unmount()
    expect(current.destroyed()).toBe(true)
    expect(disconnect).toHaveBeenCalledTimes(2)
  })

  it('handles empty maps and clears stale selection when locations disappear', async () => {
    const wrapper = mount(MapGraph, { props: { data: structuredClone(mapSample) } })
    const graph = instances[0]!
    graph.getElementById('sample-village').emit('tap')
    await wrapper.setProps({ data: { ...mapSample, nodes: [] } })
    expect(graph.destroyed()).toBe(true)
    expect(wrapper.text()).toContain('No locations to display.')
    expect(wrapper.find('.view-controls').exists()).toBe(false)
    expect(wrapper.get('[aria-label="Relationships"]').findAll('button')).toHaveLength(
      mapSample.edges.length,
    )
    await wrapper.setProps({ data: { nodes: [], edges: [], source_segment_count: 0 } })
    expect(wrapper.text()).toContain('No geographic relationships found.')
    expect(instances).toHaveLength(1)
  })

  it('rebuilds when the same reactive map changes in place', async () => {
    const data = reactive(structuredClone(mapSample))
    const wrapper = mount(MapGraph, { props: { data } })
    const graph = instances[0]!
    graph.getElementById('sample-village').emit('tap')
    data.nodes[0]!.name = 'Updated place'
    await wrapper.vm.$nextTick()
    expect(graph.destroyed()).toBe(true)
    expect(instances[1]!.getElementById('sample-village').data('label')).toBe('Updated place')
    expect(wrapper.get('[aria-label="Selection details"]').text()).toContain('Select a location')
  })

  it('renders evidence as text and lets keyboard users select dangling edges', async () => {
    const edge = {
      ...mapSample.edges[0]!,
      evidence: '<img src=x onerror=alert(1)>',
      target: 'missing',
    }
    const wrapper = mount(MapGraph, { props: { data: { ...mapSample, edges: [edge] } } })
    const buttons = wrapper.findAll('li button')
    await buttons[buttons.length - 1]!.trigger('click')
    expect(wrapper.get('[aria-label="Selection details"]').text()).toContain(
      'Silverwood Forest north of missing',
    )
    expect(wrapper.text()).toContain(edge.evidence)
    expect(wrapper.find('img').exists()).toBe(false)
    await wrapper.get('.details-heading button').trigger('click')
    expect(wrapper.find('[aria-pressed="true"]').exists()).toBe(false)
  })

  it('shows unplaced locations separately with their relationship evidence', async () => {
    const wrapper = mount(MapGraph, { props: { data: mapSample } })
    const unplaced = wrapper.get('[aria-label="Unplaced locations"]')
    expect(unplaced.findAll('button').map((button) => button.text())).toEqual(['Old Watchtower'])
    expect(instances[0]!.getElementById('sample-tower')).toHaveLength(0)
    await unplaced.get('button').trigger('click')
    const details = wrapper.get('[aria-label="Selection details"]')
    expect(details.text()).toContain('Old Watchtower')
    expect(details.text()).toContain(mapSample.edges[1]!.evidence)
    expect(details.text()).toContain('00:01:30')
  })

  it('switches independent areas and highlights the location selected through the index', async () => {
    const secondArea = {
      nodes: [
        { ...mapSample.nodes[0]!, id: 'second:a', name: 'Second area' },
        { ...mapSample.nodes[0]!, id: 'second:b', name: 'Second landmark' },
      ],
      edge: {
        ...mapSample.edges[0]!,
        id: 'second:direction',
        source: 'second:a',
        target: 'second:b',
      },
    }
    const wrapper = mount(MapGraph, {
      props: {
        data: {
          ...mapSample,
          nodes: [...mapSample.nodes, ...secondArea.nodes],
          edges: [...mapSample.edges, secondArea.edge],
        },
      },
    })
    const location = wrapper.findAll('li button').find((button) => button.text() === 'Second area')!
    await location.trigger('click')
    expect(instances[0]!.destroyed()).toBe(true)
    expect(instances[1]!.getElementById('second:a').hasClass('highlighted')).toBe(true)
    expect(instances[1]!.getElementById('sample-village')).toHaveLength(0)
    await wrapper.get('select').setValue('0')
    expect(instances[1]!.destroyed()).toBe(true)
    expect(instances[2]!.getElementById('sample-village')).toHaveLength(1)
    expect(wrapper.get('[aria-label="Selection details"]').text()).toContain('Select a location')
  })
})
