import { test, expect } from '@playwright/test';

test('dashboard renders', async ({ page }) => {
  await page.goto('/dashboard');
  await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible();
});

test('record a net worth snapshot', async ({ page }) => {
  await page.goto('/net-worth');

  // The snapshot form has one balance input per account; fill the first.
  await page.locator('input[name^="balance_"]').first().fill('12345.67');
  await page.fill('input[name="snapshot_date"]', '2026-06-20');
  await page.click('button:has-text("Save Snapshot")');

  await expect(page.getByText('Net worth snapshot saved.')).toBeVisible();
});
