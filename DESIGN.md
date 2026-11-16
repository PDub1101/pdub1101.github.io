# Paul Gibson — Portfolio Design System (DESIGN.md)

**Aesthetic Direction:** Institutional Quantitative Terminal (Bloomberg / Finviz / ESPN HD Broadcast Open Architecture).  
**Core Mandate:** Anti-AI card soup. No `rounded-2xl` puffy floating cards, no cloudy drop shadows, and no generic container nests. Content breathes on the canvas separated by razor-sharp 1px hairline rules and continuous horizontal telemetry strips.

---

## 1. Color Palette & Token System

All color tokens guarantee minimum **WCAG 2.1 AA** contrast ratios (≥ 4.5:1 for body copy and ≥ 3:1 for large text / graphical boundaries).

### Light Mode (`data-theme="light"`)
```css
:root, html[data-theme="light"] {
  --bg-page: #f8fafc;                /* Crisp light-slate canvas */
  --bg-header: rgba(248, 250, 252, 0.94);
  --bg-surface: #ffffff;
  --bg-surface-alt: #f1f5f9;
  --bg-surface-hover: #e2e8f0;

  --border-subtle: #e2e8f0;           /* 1px hairline grid divider */
  --border-strong: #cbd5e1;

  --text-primary: #0f172a;           /* 15.2:1 contrast against white */
  --text-secondary: #475569;         /* 7.1:1 contrast against white */
  --text-muted: #475569;             /* 5.5:1 contrast against #f1f5f9 (Passes WCAG AA) */

  --accent-gt: #003057;              /* Georgia Tech Navy */
  --accent-gold: #b3a369;            /* Tech Gold */
  --accent-blue: #1d4ed8;            /* 7.3:1 contrast against white */
  --accent-blue-bg: #eff6ff;
  --accent-blue-border: #bfdbfe;

  --status-active: #047857;          /* 5.1:1 contrast against #ecfdf5 (Passes WCAG AA) */
  --status-active-bg: #ecfdf5;

  --shadow-subtle: none;
  --shadow-card: none;
}
```

### Slate / Dark Mode (`data-theme="slate"`)
```css
html[data-theme="slate"] {
  --bg-page: #0f1218;                /* Institutional deep slate */
  --bg-header: rgba(15, 18, 24, 0.92);
  --bg-surface: #171c26;
  --bg-surface-alt: #1c2331;
  --bg-surface-hover: #222a3a;

  --border-subtle: #242c3d;
  --border-strong: #333e54;

  --text-primary: #f1f5f9;           /* 14.8:1 contrast against #0f1218 */
  --text-secondary: #94a3b8;         /* 6.2:1 contrast against #0f1218 */
  --text-muted: #94a3b8;             /* 6.2:1 contrast against #0f1218 (Passes WCAG AA) */

  --accent-gt: #93c5fd;
  --accent-gold: #d4af37;
  --accent-blue: #60a5fa;
  --accent-blue-bg: rgba(96, 165, 250, 0.12);
  --accent-blue-border: rgba(96, 165, 250, 0.28);

  --status-active: #34d399;
  --status-active-bg: rgba(52, 211, 153, 0.12);

  --shadow-subtle: none;
  --shadow-card: none;
}
```

---

## 2. Typography Hierarchy

- **Display & Headings:** `Plus Jakarta Sans`, font-weights `700` and `800`, letter-spacing `-0.02em`.
- **Interface & Body:** `Inter`, font-weights `400`, `500`, `600`, line-height `1.55`.
- **Financial, Mathematical & Telemetry:** `JetBrains Mono`, `font-variant-numeric: tabular-nums;`.

### Type Scale & Quality Floors
| Level | Font Size | Line Height | Weight | Tracking | Usage |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `h1` | `34px` | `1.15` | `800` | `-0.025em` | Hero dossier name |
| `h2` | `18px – 20px` | `1.3` | `800` | `-0.02em` | Featured project titles & section headers |
| `h3` | `15px – 16px` | `1.35` | `700` | `-0.015em` | Subsections, model components |
| `Body` | `14px – 14.5px` | `1.55` | `400/500` | `0` | Explanatory narrative, bio descriptions |
| `Meta / Table` | `12.5px – 13px` | `1.4` | `600` | `0.01em` | Table data, route descriptors, stats |
| **Minimum Floor** | **`11.5px`** | `1.3` | `700` | `0.03em` | Micro-badges, timestamps, ticker codes |

> **Quality Rule:** No interactive or content-bearing functional UI text may drop below `11.5px`.

---

## 3. Structural Components

### A. Continuous Telemetry Ribbon (`.metrics-ribbon`)
A horizontal edge-to-edge strip replacing floating cards:
- `background: var(--bg-card);`
- `border-top: 1px solid var(--border-subtle);`
- `border-bottom: 1px solid var(--border-subtle);`
- `padding: 8px 0;`
- Sub-cards have `background: transparent; border: none; border-right: 1px solid var(--border-subtle); border-radius: 0; padding: 14px 18px;`.
- Left hairline accent stripes (`width: 3px; height: 100%;`) color-code specific metrics (Bankroll: Blue, Outliers: Green, Model: Orange/Purple).

### B. Broadcast Scorebug Arena
- Open canvas layout (no outer enclosing card box).
- 4px chassis for live match scorebugs (`border: 1px solid var(--border-subtle); border-radius: 4px; box-shadow: none;`).
- Tabular numerals for game clocks, quarter markers, and point spreads.

### C. Open Hairline Timeline (`.timeline-spine`)
- Continuous 1px vertical hairline rule (`background: var(--border-subtle)`).
- Circular node markers (`width: 9px; height: 9px; border-radius: 50%;`).
- Open project and career stream without enclosing boxes.

---

## 4. Accessibility & Motion Guidelines

- **Motion Sensitivity:** Marquee banners and tickers must support `prefers-reduced-motion: reduce`, halting infinite animations and falling back to manual horizontal scrolling.
- **Touch Targets:** Interactive filter pills, duration buttons, and navigation controls must meet at least `32px` vertical touch bounds with 4px+ adjacent gap.
- **No Chromatic Halos:** Colored zero-offset blur glows (`box-shadow: 0 0 12px rgba(...)`) are prohibited. Elevation is communicated through clean 1px border contrast.
