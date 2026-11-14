// Stylesheets use logical properties only (margin-inline-start, not margin-left), P1 AC-9b.
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { physicalCssViolations } from "../eslint-rules/css-physical.js";

function cssFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return cssFiles(path);
    return path.endsWith(".css") ? [path] : [];
  });
}

describe("physicalCssViolations", () => {
  it("finds physical properties and values", () => {
    const css = ".a{margin-left:4px;padding-right:2px}.b{left:0;text-align:right}.c{float:left;border-top-left-radius:2px}";
    expect(physicalCssViolations(css)).toHaveLength(6);
  });
  it("accepts logical properties", () => {
    const css = ".a{margin-inline-start:4px;inset-inline-end:0;text-align:start;border-start-start-radius:2px}";
    expect(physicalCssViolations(css)).toEqual([]);
  });
  it("ignores comments", () => {
    expect(physicalCssViolations("/* margin-left is banned */ .a{margin:0}")).toEqual([]);
  });
});

describe("the portal's stylesheets", () => {
  for (const file of cssFiles(join(import.meta.dirname, "..", "src"))) {
    it(`${file} uses logical properties only`, () => {
      expect(physicalCssViolations(readFileSync(file, "utf8"))).toEqual([]);
    });
  }
});
