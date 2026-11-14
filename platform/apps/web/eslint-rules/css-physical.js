// Physical left/right in CSS (margin-left, left:, text-align: right ...), for the stylesheet test.

const PATTERNS = [
  /\b(?:margin|padding|scroll-margin|scroll-padding)-(?:left|right)\s*:/g,
  /\bborder-(?:left|right)(?:-[a-z]+)?\s*:/g,
  /\bborder-(?:top|bottom)-(?:left|right)-radius\s*:/g,
  /(?:^|[;{\s])(?:left|right)\s*:/g,
  /\b(?:text-align|float|clear)\s*:\s*(?:left|right)\b/g,
];

export function physicalCssViolations(css) {
  const code = css.replace(/\/\*[\s\S]*?\*\//g, "");
  return PATTERNS.flatMap((re) => [...code.matchAll(re)].map((m) => m[0].trim()));
}
