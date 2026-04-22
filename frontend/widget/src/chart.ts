/**
 * Vega-Lite chart rendering.
 *
 * The Cortex Agents Run API emits `response.chart` events whose `chart_spec`
 * is a Vega-Lite v5 specification (serialized as a JSON string). We render
 * them with `vega-embed`, which is dynamically imported on first use so the
 * ~260 KB gzipped plotting runtime doesn't load for text-only conversations.
 *
 * Bundled locally (no CDN) so the widget works in production environments
 * with strict CSP or outbound-network restrictions.
 *
 * Reference: https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-agents-run
 */

type VegaEmbedFn = (
  el: HTMLElement,
  spec: object,
  opts?: Record<string, unknown>,
) => Promise<unknown>;

let loader: Promise<VegaEmbedFn> | null = null;

function loadVegaEmbed(): Promise<VegaEmbedFn> {
  if (loader) return loader;
  loader = import("vega-embed")
    .then((mod) => (mod.default ?? (mod as unknown)) as VegaEmbedFn)
    .catch((err) => {
      loader = null; // allow retry on the next chart
      throw err;
    });
  return loader;
}

/**
 * Render a Vega-Lite spec into `container`. Returns a promise that resolves
 * once rendering is complete; on failure the promise rejects and the caller
 * can render a fallback.
 */
export async function renderVegaChart(
  container: HTMLElement,
  chartSpecJson: string,
  theme: "light" | "dark" = "light",
): Promise<void> {
  let spec: Record<string, any>;
  try {
    spec = JSON.parse(chartSpecJson);
  } catch (err) {
    throw new Error(`Invalid chart spec JSON: ${(err as Error).message}`);
  }

  const vegaEmbed = await loadVegaEmbed();

  // Cortex Agents sometimes emit fixed widths tuned for dashboards; adapt
  // the spec to fit our (often narrow) chat bubble instead.
  adaptSpecForNarrowContainer(spec);

  try {
    await vegaEmbed(container, spec, {
      actions: { export: true, source: false, compiled: false, editor: false },
      theme: theme === "dark" ? "dark" : undefined,
      renderer: "svg",
    });
  } catch (err) {
    // Surface the adapted spec so we can reproduce rendering issues offline.
    // eslint-disable-next-line no-console
    console.warn("[chatbot] vega-embed failed to render", { err, spec });
    throw err;
  }
}

/**
 * Mutate a Vega-Lite spec in-place so it renders well in a narrow card.
 *
 * We intentionally stay conservative here because Cortex emits a wide variety
 * of spec shapes (single-view, layer, concat, facet). Overriding `autosize`
 * or forcing `width`/`height` on multi-view specs makes Vega-Lite collapse
 * the plot area to zero width — don't do it. Config values are safe because
 * they cascade to all child views.
 */
function adaptSpecForNarrowContainer(spec: Record<string, any>): void {
  if (!spec || typeof spec !== "object") return;

  // Multi-view specs (concat/facet/repeat) don't honor top-level width/height.
  const isMultiView =
    "hconcat" in spec ||
    "vconcat" in spec ||
    "concat" in spec ||
    "facet" in spec ||
    "repeat" in spec;

  if (!isMultiView) {
    spec.width = "container";
    if (typeof spec.height !== "number") spec.height = 280;
  }
  // NOTE: do NOT override `autosize`. `fit` breaks layered/grouped specs by
  // shrinking the plot area once a bottom legend is reserved. Vega-Lite's
  // default ("pad") works correctly across every Cortex spec shape we've
  // seen so far.

  const cfg = (spec.config = spec.config ?? {});

  // Legend below the plot — inline legends eat 30–40% of the horizontal
  // room on a 300–400px bubble and push the plot into a thin strip.
  cfg.legend = {
    orient: "bottom",
    direction: "horizontal",
    labelLimit: 140,
    symbolSize: 80,
    ...cfg.legend,
  };

  // Keep axis labels from colliding on time-series specs with many ticks.
  cfg.axis = {
    labelLimit: 100,
    titleLimit: 140,
    labelOverlap: "parity",
    ...cfg.axis,
  };
  cfg.axisX = {
    labelAngle: -30,
    labelPadding: 2,
    ...cfg.axisX,
  };

  // Left-align the title so multi-line wraps look intentional.
  if (typeof spec.title === "string") {
    spec.title = { text: spec.title, anchor: "start" };
  } else if (spec.title && typeof spec.title === "object" && !("anchor" in spec.title)) {
    spec.title.anchor = "start";
  }
  cfg.title = {
    fontSize: 13,
    fontWeight: 600,
    anchor: "start",
    offset: 6,
    ...cfg.title,
  };
}
