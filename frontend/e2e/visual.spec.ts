import { expect, test, type Page } from '@playwright/test';
import { mockApi } from './fixtures';

async function capture(
  page: Page,
  theme: 'light' | 'dark',
  screen: string,
  path: string,
  heading: string,
) {
  await page.goto(path);
  await expect(
    page.getByRole('heading', { name: heading, exact: true }),
  ).toBeVisible();
  await expect(page.getByText('9,856')).toBeVisible();
  await page.screenshot({
    path: `artifacts/visuals/${screen}-${theme}-mobile.png`,
    animations: 'disabled',
  });
}

for (const theme of ['light', 'dark'] as const) {
  test(`review every primary screen (${theme})`, async ({ page }) => {
    await mockApi(page);
    await page.addInitScript((colorScheme) => {
      window.Telegram = {
        WebApp: {
          initData: 'visual-test-data',
          colorScheme,
          themeParams: {},
          ready: () => undefined,
          expand: () => undefined,
          onEvent: () => undefined,
          offEvent: () => undefined,
        },
      };
    }, theme);

    await capture(page, theme, 'catalog', '/', 'Collections');
    await capture(
      page,
      theme,
      'collection',
      '/collections/plush-pepe',
      'Plush Pepe',
    );
    await capture(
      page,
      theme,
      'pending',
      '/bets/bet-pending',
      'Waiting for verified randomness',
    );
    await capture(page, theme, 'reveal', '/bets/bet-complete', 'Gift revealed');
    await capture(page, theme, 'inventory', '/inventory', 'Virtual inventory');
    await capture(page, theme, 'history', '/history', 'Attempt history');
    await capture(
      page,
      theme,
      'audit-current',
      '/rounds/round-current/audit',
      'Round audit',
    );
    await capture(
      page,
      theme,
      'audit-disclosed',
      '/rounds/round-complete/audit',
      'Round audit',
    );
  });
}
