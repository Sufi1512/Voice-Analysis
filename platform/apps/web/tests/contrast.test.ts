// WCAG 2.2 AA in both themes (P1 non-functional requirement): text tokens >= 4.5:1 on canvas and
// panel; the focus ring and control borders >= 3:1 against the canvas (non-text contrast).
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const css = readFileSync(join(import.meta.dirname, "..", "src", "app", "globals.css"), "utf8");

function block(selector: string): Record<string, string> {
  const start = css.indexOf(`${selector} {`);
  const body = css.slice(start, css.indexOf("}", start));
  return Object.fromEntries([...body.matchAll(/--nx-([a-z-]+):\s*(#[0-9a-f]{6})/g)].map((m) => [m[1], m[2]]));
}

function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => {
    const c = parseInt(hex.slice(i, i + 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r! + 0.7152 * g! + 0.0722 * b!;
}

export function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi! + 0.05) / (lo! + 0.05);
}

const TEXT = ["text", "muted", "faint", "link", "voice", "ai", "knowledge", "good", "warn", "running", "critical"];
const SURFACES = ["canvas", "panel", "raised", "sidebar"];

for (const [theme, selector] of [["dark", ":root"], ["light", '[data-theme="light"]']] as const) {
  describe(`${theme} theme`, () => {
    const t = block(selector);
    it("defines every token", () => {
      for (const k of [...TEXT, ...SURFACES, "action", "on-action", "focus", "control"]) expect(t[k], k).toBeDefined();
    });
    for (const fg of TEXT) {
      for (const bg of SURFACES) {
        it(`${fg} on ${bg} is at least 4.5:1`, () => {
          expect(contrast(t[fg]!, t[bg]!)).toBeGreaterThanOrEqual(4.5);
        });
      }
    }
    it("button text on the action colour is at least 4.5:1", () => {
      expect(contrast(t["on-action"]!, t.action!)).toBeGreaterThanOrEqual(4.5);
    });
    it("avatar initials are at least 4.5:1", () => {
      expect(contrast(t["avatar-text"]!, t.avatar!)).toBeGreaterThanOrEqual(4.5);
    });
    it("focus ring is at least 3:1 against the canvas and panel", () => {
      expect(contrast(t.focus!, t.canvas!)).toBeGreaterThanOrEqual(3);
      expect(contrast(t.focus!, t.panel!)).toBeGreaterThanOrEqual(3);
    });
  });
}
