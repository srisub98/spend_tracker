import { test, expect } from '@playwright/test';
import path from 'path';

const fixture = (f: string) => path.join(__dirname, '..', 'fixtures', f);

test('upload a CSV: preview, confirm, and see the imported rows', async ({ page }) => {
  await page.goto('/transactions/upload');

  await page.selectOption('select[name="account_id"]', { label: 'Citi Checking (checking)' });
  await page.setInputFiles('input[name="csv_file"]', fixture('citi-checking.csv'));
  await page.click('#submit-btn');

  // Preview only — nothing is imported yet.
  await expect(page.getByText('4 rows parsed')).toBeVisible();

  await page.click('button:has-text("Looks right")');

  // Success flash on the review page (tolerant of dedup on local re-runs).
  await expect(page.getByText(/Imported \d+ new transactions/)).toBeVisible();

  // The rows are now in the transactions list, categorized by the seed rules.
  await page.goto('/transactions');
  await expect(page.getByText('WHOLE FOODS MARKET')).toBeVisible();
  await expect(page.getByText('PAYROLL DIRECT DEP ACME CORP')).toBeVisible();
});

test('uncategorized rows land in the review queue', async ({ page }) => {
  await page.goto('/transactions/upload');
  await page.selectOption('select[name="account_id"]', { label: 'Citi Double Cash (credit)' });
  await page.setInputFiles('input[name="csv_file"]', fixture('unmatched.csv'));
  await page.click('#submit-btn');
  await page.click('button:has-text("Looks right")');

  await page.goto('/transactions/review');
  await expect(page.getByText('QZX MERCHANT 4471')).toBeVisible();
  await expect(page.getByText('NORTHSIDE GENERAL STORE')).toBeVisible();
});
