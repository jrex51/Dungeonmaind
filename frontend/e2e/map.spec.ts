import { expect, test } from '@playwright/test'

test.use({ headless: true })

const sessionMap = {
  nodes: [
    { id: 'briar', name: 'Briar Hold', mentions: 1, first_seen: 20, last_seen: 20 },
    { id: 'frost', name: 'Frost Gate', mentions: 1, first_seen: 20, last_seen: 20 },
  ],
  edges: [
    {
      id: 'bearing',
      source: 'frost',
      target: 'briar',
      relation: 'north_of',
      evidence: '',
      timestamp: 20,
    },
    {
      id: 'journey',
      source: 'briar',
      target: 'frost',
      relation: 'travelled_to',
      evidence: 'We reached Frost Gate after leaving Briar Hold.',
      timestamp: 20,
    },
  ],
  source_segment_count: 1,
}

test('renders the sample campaign map, supports keyboard and mobile selection, and switches data modes', async ({
  page,
}) => {
  await page.addInitScript(() => {
    sessionStorage.setItem(
      'player',
      JSON.stringify({ id: 'map-test-player', name: 'Map tester', role: 'member' }),
    )
    localStorage.setItem('backendUrl', 'http://map-backend.test')
  })
  await page.route('http://map-backend.test/players/map-test-player/exists', (route) =>
    route.fulfill({ json: { exists: true } }),
  )
  const requests: { method: string; body: string | null }[] = []
  await page.route(/^http:\/\/map-backend\.test\/map(?:\/generate)?$/, (route) => {
    const method = route.request().method()
    requests.push({ method, body: route.request().postData() })
    return route.fulfill({
      json: method === 'GET' ? sessionMap : { nodes: [], edges: [], source_segment_count: 0 },
    })
  })
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))

  await page.goto('/map?demo=sample')
  await expect(page.getByText('Sample demo with fictional locations and evidence.')).toBeVisible()
  await expect(page.locator('.graph-canvas canvas').first()).toBeVisible()
  await expect(page.getByRole('alert')).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Generate Map' })).toBeDisabled()
  expect(requests).toEqual([])

  const willowbrook = page.getByRole('button', { name: 'Willowbrook', exact: true })
  await willowbrook.focus()
  await page.keyboard.press('Enter')
  const details = page.getByRole('region', { name: 'Selection details' })
  await expect(details).toContainText('00:00:10')
  await expect(details).toContainText('Sample: Silverwood Forest lies north of Willowbrook.')
  await expect(details).toContainText('00:00:30')
  await page.keyboard.press('Escape')
  await expect(willowbrook).toHaveAttribute('aria-pressed', 'false')
  await expect(details).toContainText('Select a location')
  await page.getByRole('button', { name: 'Willowbrook travelled to Silverwood Forest' }).click()
  await expect(details).toContainText('Sample: The party travelled from Willowbrook to the forest.')
  await expect(details).toContainText('00:02:00')
  await page.getByRole('button', { name: 'Clear selection' }).click()
  await expect(details).toContainText('Select a location')
  await page.getByRole('button', { name: 'Fit to View' }).click()
  await page.screenshot({ path: test.info().outputPath('map-desktop.png'), fullPage: true })

  await page.setViewportSize({ width: 390, height: 844 })
  await expect(page.locator('.graph-canvas')).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  )
  const unplaced = page.getByRole('region', { name: 'Unplaced locations' })
  await unplaced.getByRole('button', { name: 'Old Watchtower' }).click()
  await expect(details).toBeInViewport()
  await expect(details).toContainText('Sample: The old watchtower stands inside Silverwood Forest.')
  await expect(details).toContainText('00:01:30')
  await page.screenshot({ path: test.info().outputPath('map-mobile.png'), fullPage: true })

  await page.getByRole('button', { name: 'Use session data' }).click()
  await expect(page.getByRole('button', { name: 'Frost Gate', exact: true })).toBeVisible()
  await expect(page.getByText('Willowbrook', { exact: true })).toHaveCount(0)
  expect(requests).toEqual([{ method: 'GET', body: null }])

  // The only route is vertical and spans the center of the fitted canvas.
  const canvas = page.locator('.graph-canvas')
  await canvas.scrollIntoViewIfNeeded()
  const bounds = (await canvas.boundingBox())!
  const center = { x: bounds.width / 2, y: bounds.height / 2 }
  await canvas.click({ position: center })
  await expect(details).toContainText('We reached Frost Gate after leaving Briar Hold.')
  await expect(details).toContainText('00:00:20')

  await page.getByRole('button', { name: 'Generate Map' }).click()
  await expect(page.getByText('No geographic map yet')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Generate Map' })).toBeEnabled()
  expect(requests).toEqual([
    { method: 'GET', body: null },
    { method: 'POST', body: null },
  ])
  await page.getByRole('button', { name: 'Show sample demo' }).click()
  await expect(page.locator('.graph-canvas canvas').first()).toBeVisible()
  await expect(details).toContainText('Select a location')
  expect(requests).toHaveLength(2)
  expect(errors).toEqual([])
})
