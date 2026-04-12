# The Glass Terminal: Design Philosophy & Technical Execution

## Core Manifesto

Institutional financial tools look like spreadsheets from 2004. To command a premium in the prosumer market, this application cannot just display data—it must act as a next-generation instrument. It merges the ruthless efficiency of a Bloomberg Terminal with the fluid, effortless aesthetics of modern OS interfaces. We call this philosophy **"Tactical Precision."**

---

## Pillar 1: Spatial Architecture (The Workspace, Not a Webpage)

The fundamental flaw of most web-based SaaS apps is that they treat data like a blog post—forcing users to scroll up and down. A premium trading tool is an environment.

- **The Zero-Scroll Mandate:** The user's screen is an arena. Lock the interface to the exact dimensions of their monitor (`100vh`). If a user has to touch their scroll wheel to find critical telemetry, the layout has failed. Everything is visible at a glance, anchored in place.
- **The Asymmetrical Bento Grid:** Hierarchy requires imbalance. Divide your screen mathematically:
  - **The Map (65% Width):** The Volatility Regime Indicator is the spatial map of the market. It gets the vast majority of the real estate on the left.
  - **The Telemetry (35% Width):** Key metrics (VOL, SPREAD, SKEW, CONVEXITY) sit on the right, stacked in a perfectly aligned 2x2 grid. They are the dashboard gauges.
- **Proximity Over Borders:** Amateurs use thick lines to separate sections. Professionals use negative space. Strip away hard borders. Use generous, consistent blank space to let the user's brain naturally group the elements together.

## Pillar 2: The Visual Language of Illumination

Move away from standard "dark mode" (murky grey websites) to something that feels physical and light-emitting.

- **The Void (Canvas Context):** The absolute background of your app should be a deep, rich off-black (like midnight slate). Pure `#000000` causes eye strain with bright text. Use a background that absorbs light, making the data feel like it’s floating in a void.
- **Frosted Materiality:** Metric cards are not flat rectangles; they are sheets of smoked glass. They need a background color only 2% lighter than the canvas, a microscopic (1px) semi-transparent white inner border to catch "light," and a highly diffused, soft drop-shadow to float a millimeter above the background.
- **Data as Neon:** If the background absorbs light, the data must emit it. Charts, lines, and progress bars should have a subtle "glow" (shadow). They are neon gas inside a glass tube.
- **Eradicate "Murkiness":** Colored quadrants on the main chart (Stress, Calm) must not be heavy blocks of color. They must become incredibly faint, atmospheric radial gradients in the corners. The background should whisper; the data points should scream.

## Pillar 3: Micro-Typography & Information Hierarchy

In a data-dense application, typography dictates what the user reads first, second, and third, solely through font weight and color contrast.

- **The "Data First" Rule:** The actual numbers (e.g., "88th", "11th") are the product. They must be massive, stark white, and tightly spaced.
- **Muted Context:** Labels (e.g., "ATM IV 7D", "Term Spread") are secondary. Make them tiny, uppercase, widely spaced (tracked out), and a muted ghost grey. They should visually recede until the user actively looks for them.
- **Ruthless Color Discipline:** Color must mean something. Do not use red, green, or blue for decoration. Green = "bullish/safe." Red = "bearish/danger." Keep the UI strictly monochromatic (blacks, greys, stark whites) and let the actual data provide the bursts of color.

## Pillar 4: Kinetic Interaction & Progressive Disclosure

A premium app reacts to the user's presence, feeling physical and alive.

- **The Illusion of Weight:** When a mouse glides over a metric card, it should feel tactile. The card should gracefully, physically lift toward the user by 1% and cast a slightly deeper shadow, returning softly when the mouse leaves.
- **Cross-Pollinated Systems:** The app must act as one connected brain. Hovering over the "SKEW" metric card on the right should instantly react with the main Volatility Chart on the left—fading out irrelevant historical points and highlighting where the current skew fits into the visual map.
- **Concealed Complexity (Progressive Disclosure):** Do not break immersion with walls of text. A tight, glanceable narrative (≤3 sentences) earns its place inline as a full-width glass strip at the base of the workspace — it is part of the zero-scroll arena. Longer commentary and multi-section deep-dives still belong behind a sleek trigger, sweeping in as a blurred glass panel that delivers the payload over the metrics and is swiftly dismissed. Rule of thumb: if the reader can absorb it in one breath, show it; otherwise, conceal it.

## Pillar 5: Cognitive Ergonomics (Signal vs. Noise)

Your tool's job is to reduce decision fatigue and cognitive load.

- **Assassinate the Grid Lines:** Kill vertical and horizontal grid lines, axis borders, and tick marks on the main chart. Keep only the absolute minimum required to read the chart. Let the glowing data line float.
- **Contextual Tooltips:** Tooltips shouldn't be clunky, opaque squares. They should be beautifully styled, frosted glass elements that flawlessly format the data (e.g., "Volatility: 60") rather than dumping raw values.
- **Uniform Stress Orientation:** Every percentile displayed in the product reads the same way — higher means more stress, lower means more calm. Where a metric's raw statistical percentile runs against that grain (e.g., 25Δ Risk Reversal, where extreme *negative* values signal fear and thus sit at the bottom of the statistical distribution), the display is inverted to `100 - raw` at the component layer. This is a presentation choice — the underlying data in `metric_series_1m.percentile` remains the canonical statistical percentile, so analytical queries and future consumers are not corrupted. The orientation is declared per-metric via `MetricMeta.stressDirection` and mirrors the backend's `_STRESS_DIRECTION_ALIGNS` convention.

---

## Technical Execution Roadmap

The existing foundation is incredibly solid. Here is how to weaponize it:

### 1. Framework Stack

- **Next.js 16 + React 19**
- **Tailwind CSS v4** (Utility styling and design tokens)
- **Framer Motion** (Animation and physics engine)
- **ECharts** (Data visualization)

### 2. Tailwind v4 (`@theme`) Execution

Strip out utility classes used for hard borders and lock in exact colors:

- **Canvas:** Deep background (e.g., `#09090b`).
- **Surfaces:** Glass cards using `rgba(255, 255, 255, 0.02)` and hover states at `0.04`.
- **Strokes:** Faint edge lighting `rgba(255, 255, 255, 0.06)`.
- **Foregrounds:** Pure white for data (`#fafafa`), Zinc-400 for labels (`#a1a1aa`), Zinc-600 for inactive elements (`#52525b`).

### 3. Framer Motion Integration

Use Framer Motion for all hover states and the sweeping "Insights" side-panel. Wrap cards in `<motion.div>` and apply spring-physics for tactile interactions (e.g., `whileHover={{ scale: 1.01, y: -2 }}`).

### 4. ECharts Aggressive Theming

Dive into the ECharts configuration object to remove default corporate styling:

- Set `splitLine: false` everywhere.
- Add `shadowColor` and `shadowBlur` to `lineStyle` to achieve the neon glow.
- Use `tooltip.formatter` to inject custom HTML so tooltips match the frosted-glass aesthetic (`backdrop-filter: blur()`, semi-transparent backgrounds) of the surrounding Next.js components.
