import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';
import { mockApi } from './fixtures';

const screens = [
  ['/', 'Collections'],
  ['/collections/plush-pepe', 'Plush Pepe'],
  ['/bets/bet-pending', 'Waiting for verified randomness'],
  ['/bets/bet-complete', 'Gift revealed'],
  ['/inventory', 'Virtual inventory'],
  ['/history', 'Attempt history'],
  ['/rounds/round-current/audit', 'Round audit'],
  ['/rounds/round-complete/audit', 'Round audit'],
] as const;

async function useTelegramTheme(page: Page, theme: 'light' | 'dark') {
  await page.addInitScript((colorScheme) => {
    window.Telegram = {
      WebApp: {
        initData: 'accessibility-test-data',
        colorScheme,
        themeParams: {},
        ready: () => undefined,
        expand: () => undefined,
        onEvent: () => undefined,
        offEvent: () => undefined,
      },
    };
  }, theme);
}

for (const theme of ['light', 'dark'] as const) {
  test(`primary screens have no serious accessibility violations (${theme})`, async ({
    page,
  }) => {
    await mockApi(page);
    await useTelegramTheme(page, theme);
    await page.emulateMedia({ reducedMotion: 'reduce' });

    for (const [path, heading] of screens) {
      await page.goto(path);
      await expect(
        page.getByRole('heading', { name: heading, exact: true }),
      ).toBeVisible();
      const results = await new AxeBuilder({ page })
        .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
        .analyze();
      const serious = results.violations.filter(
        (violation) =>
          violation.impact === 'serious' || violation.impact === 'critical',
      );
      expect(
        serious.map(({ id, impact, nodes }) => ({
          id,
          impact,
          targets: nodes.map((node) => node.target),
        })),
        `${path} (${theme})`,
      ).toEqual([]);
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= window.innerWidth,
        ),
        `${path} must not overflow the mobile viewport`,
      ).toBe(true);
    }
  });
}

test('keyboard users can operate theme and primary navigation', async ({
  page,
}) => {
  await mockApi(page);
  await useTelegramTheme(page, 'light');
  await page.goto('/');
  await expect(
    page.getByRole('heading', { name: 'Collections' }),
  ).toBeVisible();

  await page.keyboard.press('Tab');
  await expect(
    page.getByRole('link', { name: 'GwenGift catalog' }),
  ).toBeFocused();
  await page.keyboard.press('Tab');
  const themeButton = page.getByRole('button', {
    name: 'Switch to dark theme',
  });
  await expect(themeButton).toBeFocused();
  await expect(themeButton).toHaveCSS('outline-style', 'solid');
  await page.keyboard.press('Enter');
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');

  const inventory = page
    .getByRole('navigation', { name: 'Primary navigation' })
    .getByRole('link', { name: 'Inventory' });
  await inventory.focus();
  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(/\/inventory$/);
  await expect(
    page.getByRole('heading', { name: 'Virtual inventory' }),
  ).toBeVisible();
});

test('reduced motion disables reveal, loading, and pending animations', async ({
  page,
}) => {
  await mockApi(page);
  await useTelegramTheme(page, 'light');
  await page.emulateMedia({ reducedMotion: 'reduce' });

  await page.goto('/bets/bet-complete');
  await expect(page.locator('.gift-reveal')).toBeVisible();
  await expect(page.locator('.gift-reveal')).toHaveCSS(
    'animation-name',
    'none',
  );
  await expect(page.locator('.gift-orb')).toHaveCSS('animation-name', 'none');

  await page.goto('/bets/bet-pending');
  await expect(page.locator('.pending-spinner')).toHaveCSS(
    'animation-name',
    'none',
  );
});

test('loading is announced and transitions to catalog content', async ({
  page,
}) => {
  await mockApi(page);
  await useTelegramTheme(page, 'light');
  await page.route('**/api/collections', async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 250));
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ collections: [], asset_mode: 'simulated' }),
    });
  });
  await page.goto('/');
  const loading = page
    .getByRole('status')
    .filter({ hasText: 'Loading collections…' });
  await expect(loading).toBeVisible();
  await expect(loading).toHaveCSS('animation-name', 'loading-pulse');
  await expect(page.getByText('No collections are configured.')).toBeVisible();
  await expect(loading).toHaveCount(0);
});

test('catalog uses a two-column layout without overflow on desktop', async ({
  page,
}) => {
  await page.setViewportSize({ width: 1024, height: 900 });
  await mockApi(page);
  await useTelegramTheme(page, 'light');
  await page.goto('/');
  const cards = page.getByRole('article');
  await expect(cards).toHaveCount(10);
  const first = await cards.nth(0).boundingBox();
  const second = await cards.nth(1).boundingBox();
  expect(first).not.toBeNull();
  expect(second).not.toBeNull();
  expect(Math.abs((first?.y ?? 0) - (second?.y ?? 1))).toBeLessThan(2);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
});
