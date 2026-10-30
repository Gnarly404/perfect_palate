const { test, expect } = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;

const publicPages = [
  '/',
  '/sign-in',
  '/forgot-password',
  '/recipes/tips',
];

for (const path of publicPages) {
  test(`accessibility: ${path}`, async ({ page }) => {
    test.setTimeout(120000);
    await page.emulateMedia({ reducedMotion: 'reduce' });
    if (path === '/') {
      await page.route('**/static/frames/**', (route) => {
        const frameNumber = Number(route.request().url().match(/f(\d+)\.webp$/)?.[1]);
        return frameNumber < 8 ? route.continue() : route.abort();
      });
    }
    await page.goto(path, { waitUntil: 'domcontentloaded' });
    if (path === '/sign-in') {
      await expect(page.locator('#noteEl')).toHaveCSS('opacity', '1');
      await expect(page.locator('#authCard')).toHaveCSS('opacity', '1');
    }
    const results = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze();

    expect(
      results.violations.map(({ id, impact, help, nodes }) => ({
        id,
        impact,
        help,
        elements: nodes.map(({ target, failureSummary }) => ({
          target,
          failureSummary,
        })),
      })),
    ).toEqual([]);
  });
}

test('CSRF token is attached to same-origin fetch requests', async ({ page }) => {
  await page.goto('/sign-in', { waitUntil: 'domcontentloaded' });
  let requestHeaders;
  await page.route('**/sign-in', async (route) => {
    requestHeaders = route.request().headers();
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: '{}',
    });
  });
  await page.evaluate(async () => {
    await fetch('/sign-in', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    });
  });

  expect(requestHeaders['x-csrf-token']).toBeTruthy();
});

test('homepage frame sequence loads from the HTTP server', async ({ page }) => {
  const frameResponses = [];
  page.on('response', (response) => {
    if (response.url().includes('/static/frames/')) {
      frameResponses.push(response);
    }
  });

  await page.goto('/', { waitUntil: 'domcontentloaded' });
  await expect(page.locator('#loader')).toHaveClass(/hidden/);

  expect(frameResponses.length).toBeGreaterThanOrEqual(8);
  expect(frameResponses.slice(0, 8).every((response) => response.ok())).toBe(true);
  expect(frameResponses.every((response) => response.url().startsWith('http://'))).toBe(true);
});
