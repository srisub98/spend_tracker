import { test, expect } from '@playwright/test';

test('create an outing and add a participant', async ({ page }) => {
  await page.goto('/splits');

  await page.fill('input[name="title"]', 'Test Dinner');
  await page.fill('input[name="outing_date"]', '2026-06-21');
  await page.click('button:has-text("Create")');

  // Redirected to the new outing's detail page.
  await expect(page.getByRole('heading', { name: 'Test Dinner' })).toBeVisible();

  // Add a participant from the "Add Person" card (scoped to avoid the "Add Expense" button).
  await page.fill('input[name="name"]', 'Alex');
  await page.locator('.card', { hasText: 'Add Person' }).getByRole('button', { name: 'Add' }).click();

  await expect(page.getByText('Alex')).toBeVisible();
});
