import { test, expect } from '@playwright/test';

// These ride on the demo dataset seeded by `seed_test_db.py --demo` (see
// playwright.config.ts): sheet history, live transactions, net-worth snapshots +
// holdings, and bill splits. They assert the data-driven pages and both
// exporters render real content rather than empty stubs.

test('dashboard shows cashflow rows built from sheet history + live data', async ({ page }) => {
  await page.goto('/dashboard');

  await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible();
  // Income / expense pivot rows (server-rendered, not animated).
  await expect(page.getByRole('cell', { name: 'Total Income' })).toBeVisible();
  await expect(page.getByRole('cell', { name: 'Total Expenses' })).toBeVisible();
  await expect(page.getByRole('cell', { name: 'Paycheck' })).toBeVisible();
  await expect(page.getByRole('cell', { name: 'Rent + Utilities' }).first()).toBeVisible();
  // Year switcher offers both the live year and the bootstrapped history year.
  await expect(page.locator('body')).toContainText('2025');
});

test('net worth page renders the account grid and holdings', async ({ page }) => {
  await page.goto('/net-worth');

  await expect(page.getByRole('heading', { name: 'Net Worth', exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: /Account Balances/ })).toBeVisible();
  await expect(page.getByRole('heading', { name: /Holdings as of/ })).toBeVisible();
  // The retirement account (demo-only) and a seeded holding both show up.
  await expect(page.getByText('Fidelity 401k').first()).toBeVisible();
  await expect(page.getByText('VTI').first()).toBeVisible();
});

test('splits page shows the outstanding receivable and outings', async ({ page }) => {
  await page.goto('/splits');

  await expect(page.getByRole('heading', { name: 'Bill Splits' })).toBeVisible();
  // $850 outstanding: Tahoe (Alex+Sam) + Birthday (Priya+Maya); Chris settled.
  await expect(page.getByText(/Outstanding \(\$850\.00 total\)/)).toBeVisible();
  await expect(page.getByRole('link', { name: 'Tahoe Ski Trip' })).toBeVisible();
  await expect(page.getByText('Alex').first()).toBeVisible();
});

test('export an Excel workbook', async ({ page }) => {
  await page.goto('/export');
  await page.click('button:has-text("Export Excel")');
  await expect(page.getByText(/Excel exported: finance_.*\.xlsx/)).toBeVisible();
  // The generated file is listed under Recent Exports.
  await expect(page.getByText(/finance_.*\.xlsx/).first()).toBeVisible();
});

test('export a self-contained HTML dashboard', async ({ page }) => {
  await page.goto('/export');
  await page.click('button:has-text("Export HTML")');
  await expect(page.getByText(/HTML dashboard exported: dashboard_.*\.html/)).toBeVisible();
});
