import axe from "axe-core";

/**
 * Run axe-core against rendered DOM and return readable violations.
 * - `color-contrast` is disabled: jsdom cannot compute colours. Token contrast is verified by
 *   `scripts/check_contrast.py` instead.
 * - `region` is disabled for isolated components (they are not full pages); shell tests
 *   pass `{ page: true }` to keep it on.
 */
export async function axeViolations(
  container: Element,
  options: { page?: boolean } = {},
): Promise<string[]> {
  // The `region` rule only evaluates landmarks when run against the whole document, so page
  // checks use `document` (verified by src/test/axe.test.tsx).
  const context = options.page === true ? document : container;
  const results = await axe.run(context, {
    rules: {
      "color-contrast": { enabled: false },
      region: { enabled: options.page === true },
    },
  });
  return results.violations.map((v) => `${v.id}: ${v.help} (${v.nodes.length} node(s))`);
}
