# Handoff: Finance Tracker — Minimalist Redesign

## Overview
A full visual redesign of the existing Flask/Jinja **Finance Tracker** app. The goal: a more robust, polished UI with a **minimalist warm-neutral palette** (color reserved strictly for up/down figures) and **tasteful animation** (count-ups, sparklines, staggered reveals, animated charts). This package covers the five primary screens: Dashboard, Transactions, Net Worth, Accounts, and Life.

## About the Design Files
The files in this bundle (`Dashboard.html`, `Transactions.html`, `Net Worth.html`, `Accounts.html`, `Life.html`, `styles.css`, `app.js`, `dashboard-data.js`) are **design references created as standalone HTML prototypes**. They show the intended look, motion, and behavior — they are **not** meant to be shipped as-is.

The existing app is **Flask + Jinja2** with a single shared `static/css/main.css` and `static/js/main.js`, extending a `templates/base.html`. **The task is to recreate this design inside that existing environment**: port `styles.css` → `static/css/main.css`, port `app.js` → `static/js/main.js`, and update the Jinja templates' markup/classes to match the prototypes. All real data already exists in the Jinja context (`d.income_rows`, `grid.net_worth`, `transactions`, etc.) — the prototype's hardcoded JS data is only for demonstration and should be replaced by the existing server-rendered values.

## Fidelity
**High-fidelity (hifi).** Final colors, typography, spacing, radii, shadows, and interactions are all specified below and present in `styles.css`. Recreate pixel-accurately, reusing the class names already in the prototypes (they intentionally match the app's existing class vocabulary: `.stat-card`, `.data-table`, `.pivot-table`, `.badge`, `.btn`, `.card`, etc.).

---

## Design Tokens
All defined as CSS custom properties in `styles.css` `:root`.

### Color — Surfaces
| Token | Value | Use |
|---|---|---|
| `--bg` | `#f5f4f1` | Page background (warm off-white) |
| `--surface` | `#ffffff` | Cards, tables, inputs |
| `--surface-2` | `#fbfbf9` | Subtle fills, table headers, hover |
| `--border` | `#e9e7e1` | Default borders |
| `--border-soft` | `#f0eee9` | Inner row dividers |
| `--border-strong` | `#dcd9d1` | Input borders, button outlines |

### Color — Ink (text)
| Token | Value | Use |
|---|---|---|
| `--ink` | `#1a1916` | Headings, primary values, accent |
| `--text` | `#2c2a26` | Body text |
| `--muted` | `#79756c` | Secondary/label text |
| `--faint` | `#a8a399` | Tertiary, dashes, placeholders |

### Color — Figures only (never used for chrome)
| Token | Value | Use |
|---|---|---|
| `--pos` / `--pos-soft` | `#2f7a55` / `#e9f1ec` | Positive amounts, up trends |
| `--neg` / `--neg-soft` | `#b1564b` / `#f4ebe9` | Negative amounts, down trends |
| `--amber` / `--amber-soft` | `#9a7322` / `#f4eede` | Warnings, "Claude" category source |

### Color — Chart tonal scale
`--c-ink #1a1916` · `--c-slate #8a857a` · `--c-green #2f7a55` · `--c-clay #b1564b` · `--c-amber #b78a3a`

> **Accent = near-black.** This is the core minimalist decision: primary buttons, active nav, the hero KPI card, and focus rings are all `--ink`. Green/red appear ONLY on numeric figures and their trend chips — never on buttons, nav, or backgrounds.

### Radius
`--radius 14px` (cards) · `--radius-sm 9px` (buttons, inputs) · `--radius-xs 6px` (nav items, pagination)

### Shadows
| Token | Value |
|---|---|
| `--shadow-sm` | `0 1px 2px rgba(26,25,22,.04), 0 1px 1px rgba(26,25,22,.03)` |
| `--shadow-md` | `0 6px 22px -8px rgba(26,25,22,.10), 0 2px 7px -3px rgba(26,25,22,.06)` |
| `--shadow-lg` | `0 18px 44px -16px rgba(26,25,22,.18), 0 6px 14px -8px rgba(26,25,22,.08)` |

### Easing
`--ease cubic-bezier(.22,.61,.36,1)` · `--ease-out cubic-bezier(.16,1,.3,1)`

### Typography
- **UI font:** `'Hanken Grotesk'` (Google Fonts, weights 400/500/600/700), fallback system sans.
- **Mono/figures:** `'JetBrains Mono'` (weights 400/500/600) for `.mono` cells (dates, amounts, table data).
- **Tabular numerics:** `.num` and `.mono` set `font-variant-numeric: tabular-nums` so columns align.
- Base body: `14.5px`, line-height `1.55`, antialiased.

| Element | Size | Weight | Letter-spacing |
|---|---|---|---|
| Page `h1` | `1.7rem` | 700 | `-.03em` |
| Card `h2` | `.95rem` | 600 | `-.01em` |
| Hero stat value | `2.5rem` | 700 | `-.035em` |
| Stat value | `1.85rem` | 700 | `-.035em` |
| Stat label | `.72rem` uppercase | 600 | `.07em` |
| Table header `th` | `.72rem` uppercase | 600 | `.06em` |
| Nav link | `.89rem` | 500 | `-.01em` |

---

## Screens / Views

### 1. Dashboard (`Dashboard.html`, data in `dashboard-data.js`)
**Purpose:** Fiscal-year overview of income, expenses, and cash flow.

**Layout:** Sticky glassy top nav → `main` (max-width `1180px`, padding `28px 22px 80px`) → page header with year segmented control → KPI `.stat-grid` → cashflow `.chart-card` → three `.card.table-scroll` pivot tables (Income, Expenses, Net Income).

**Components:**
- **Page header:** `<h1>Dashboard</h1>` + muted `.sub` "Fiscal year overview" + a `.spacer` + `.year-selector` (segmented control; active item = white pill `--surface` with `--shadow-sm`).
- **KPI grid:** `.stat-grid` = CSS grid `repeat(auto-fit, minmax(186px, 1fr))`, gap `14px`. Cards:
  - **Hero card** (`.stat-card.is-hero`, `grid-column: span 2`): background `--ink`, white text. Label "Net Income · 2025", value `$50,000` (count-up), trend chip `▲ 14.2%`, note "vs $50,000 in 2024", white sparkline.
  - Five regular `.stat-card`s: Income (`$500,000`, green value), Expenses (`$50,000`, red value), Savings Rate (`50.1%`), Invested (`$50,000`), Free Cash Flow (`$50,000`). Each has a label, count-up value, a `.trend` chip, and a colored `.spark` sparkline.
  - Hover: `translateY(-2px)` + `--shadow-md`.
- **Cashflow chart:** `.card.chart-card` with `<canvas id="cashflowChart">`. Chart.js combo: green income bars + clay expense bars (`borderRadius:5`, `maxBarThickness:16`) + ink net line (`tension .35`, no points). Custom `.legend` below.
- **Pivot tables:** `.data-table.pivot-table` inside `.card.table-scroll`. First column sticky-left. Numeric cells `.num.mono` right-aligned. Zero values render as a faint em-dash. `.total-col` (left border) and `.total-row` (top border, bold ink). `% Inc` column dim.

### 2. Transactions (`Transactions.html`)
**Purpose:** Browse, filter, recategorize, and delete transactions.

**Layout:** Page header with action buttons → `.filter-bar` → meta count → `.table-wrap` data table → `.pagination`.

**Components:**
- **Header buttons:** `↑ Upload CSV` (`.btn`), `⚠ Review 12` (`.btn.btn-warning`), `+ Add` (`.btn.btn-primary`).
- **Filter bar:** `.filter-bar` = white rounded card holding two `<select>` (Accounts, Categories), two `<input type=date>`, Filter button, Clear ghost button. Inputs `width:auto`.
- **ExampleCo:** `<strong>1,284</strong> transactions` with the count animating up.
- **Table:** `.table-wrap` (rounded, bordered, overflow-hidden) wrapping `.data-table`. Columns: Date (`.mono.dim`), Account, Description (`.desc`, ellipsis, max 300px), Amount (`.num.mono`, green if ≥0 with `+`, red with `−`), Category, delete. Category cell = a flex row with `<select class="category-select">` + a source `.badge`.
- **Source badges:** `.badge-user` (neutral, ✎), `.badge-rule` (green, ⚙), `.badge-claude` (amber, ✦), `.badge-none` (red). Changing the select flips the badge to "✎ user" and flashes a green focus ring for 900ms (mirrors the app's existing `POST /transactions/<id>/category` behavior).
- **Pagination:** `.pagination`, active page = ink fill, white text.

### 3. Net Worth (`Net Worth.html`)
**Purpose:** Track net worth over time, by asset class, with holdings and snapshot recording.

**Layout:** Header + year selector → 3-card `.stat-grid` (hero Current Net Worth `$500,000` + vs Last Month + vs Last Year) → stacked area `.chart-card` → Account Balances pivot (`.grid-class-row` subtotals per class, `.total-row` net worth) → Holdings table → `.two-col` (Record Snapshot form | Snapshot History scroll list).
- **Area chart:** Chart.js stacked line, fill at `color+'22'`, classes colored ink/green/slate/amber.
- **Snapshot form:** `.balance-row`s (label + `em.dim` asset class + right-aligned `140px` number input).

### 4. Accounts (`Accounts.html`)
**Purpose:** List linked accounts; add a new one.
**Layout:** `.two-col` — left `.card` "Your Accounts" with `.list-row`s (square `.list-ic` initial badge + name/subtype + mono balance + delete icon); right `.card` "Add Account" form (Name, Type, Asset Class selects, liability checkbox).

### 5. Life (`Life.html`)
**Purpose:** Declare fixed monthly "needed" costs vs discretionary.
**Layout:** Header + intro `.meta` → 4-card `.stat-grid` (hero Needed/month `$5,000` + Base Pay + Avg Actual Spend + Discretionary) → `.two-col` (needed-items `.data-table` with `.total-row`; inactive rows at `opacity:.45` → "Add Item" form). Category cells use `.badge`.

---

## Interactions & Behavior
All in `app.js`, guarded by `prefers-reduced-motion`.

- **Count-ups:** any `[data-count]` element animates 0 → value over ~1.1s with a cubic ease-out. Attributes: `data-prefix` (e.g. `$`), `data-suffix` (`%`), `data-decimals`. Uses `toLocaleString('en-US')`.
- **Sparklines:** `<svg class="spark" data-values="a,b,c…" data-color="…">`. `app.js` builds a normalized path + faint area fill, then animates the line drawing in via `stroke-dashoffset` over 1.3s.
- **Reveal on scroll:** elements with `.reveal` start hidden (`opacity:0; translateY(14px)`) and transition in when an `IntersectionObserver` fires; `data-delay` (seconds) staggers them.
- **Entrance:** nav slides/fades in (`nav-in`, .6s); page header rises (`rise`, .5s).
- **Charts:** Chart.js `easeOutQuart`, 1s. Shared theme via `FT.theme()` / `FT.colors()` (tooltip = ink background, white title).
- **Hover:** cards lift + deepen shadow; table rows tint `--surface-2`; buttons depress 1px on `:active`.

### Critical robustness pattern (must preserve)
The hidden/animated states are gated behind a `js` class on `<html>`, set by an inline script in each `<head>`:
```html
<script>document.documentElement.classList.add('js');</script>
```
CSS hides `.reveal` only under `html.js .reveal`, and entrance animations only under `html.js nav` / `html.js .page-header`. **Without JS the page renders fully visible** — never invisible. In Jinja, add the inline script to `base.html`'s `<head>`. `prefers-reduced-motion: reduce` also forces everything visible and kills animation.

## State Management
The prototype is static; the real app is server-rendered. No new client state required beyond what already exists. The only client interaction is the inline category change (existing `fetch` POST in the current `transactions/index.html`) — keep that, just update the success affordance to flip the badge + flash a green focus ring as shown.

## Animation values (quick reference)
| Animation | Duration | Easing | Property |
|---|---|---|---|
| Count-up | 1100ms | `1-(1-t)³` | textContent |
| Sparkline draw | 1300ms | `cubic-bezier(.16,1,.3,1)` | stroke-dashoffset |
| Reveal | 600ms | `--ease-out` | opacity, transform |
| Nav in | 600ms | `--ease-out` | opacity, translateY |
| Card hover | 300ms | `--ease` | shadow, transform |
| Chart | 1000ms | easeOutQuart | — |

## Assets
- **Fonts:** Hanken Grotesk + JetBrains Mono via Google Fonts `@import` at the top of `styles.css`. Self-host in production if preferred.
- **Charts:** Chart.js `4.4.0` (already used by the app).
- **Icons:** Unicode glyphs only (▲ ▼ ✎ ⚙ ✦ ✕ ↑ ⚠). No image assets. The brand mark is a CSS square with the letter "F".

## Files
| File | Role |
|---|---|
| `styles.css` | Full design system → port to `static/css/main.css` |
| `app.js` | Count-ups, reveals, sparklines, `FT` chart theme → port to `static/js/main.js` |
| `Dashboard.html` + `dashboard-data.js` | Dashboard reference → `templates/dashboard/index.html` |
| `Transactions.html` | → `templates/transactions/index.html` |
| `Net Worth.html` | → `templates/net_worth/index.html` |
| `Accounts.html` | → `templates/accounts/index.html` |
| `Life.html` | → `templates/life/index.html` |

> Pages not yet redesigned (use the same system to extend): Rules, Equities, Splits, Export. The nav markup lives in every prototype's `<nav>` — move it into `base.html` and drive `active` from `request.blueprint` as the app already does.
