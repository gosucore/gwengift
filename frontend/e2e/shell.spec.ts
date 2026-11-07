import { expect, test, type Page } from '@playwright/test';

const account = {
  telegram_user_id: 1001,
  username: 'mobile-player',
  demo_balance: 10000,
  active_epoch: 1,
  asset_mode: 'simulated',
};

async function mockAccount(page: Page) {
  await page.route('**/api/account', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(account),
    }),
  );
  await page.route('**/api/collections', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ collections: [], asset_mode: 'simulated' }),
    }),
  );
}

for (const theme of ['light', 'dark'] as const) {
  test(`mobile shell has no real-asset actions (${theme})`, async ({
    page,
  }) => {
    await mockAccount(page);
    await page.addInitScript((colorScheme) => {
      window.Telegram = {
        WebApp: {
          initData: 'screenshot-test-data',
          colorScheme,
          themeParams: {},
          ready: () => undefined,
          expand: () => undefined,
          onEvent: () => undefined,
          offEvent: () => undefined,
        },
      };
    }, theme);
    await page.goto('/');
    await expect(page.getByText('10,000')).toBeVisible();
    await expect(page.getByText('SIMULATION · DEMO ASSETS ONLY')).toBeVisible();
    await expect(
      page.getByRole('button', { name: /purchase|withdraw|wallet/i }),
    ).toHaveCount(0);
    await expect(
      page.getByRole('link', { name: /purchase|withdraw|wallet/i }),
    ).toHaveCount(0);
    await page.screenshot({
      path: `artifacts/shell-${theme}-mobile.png`,
      fullPage: true,
    });
  });
}
