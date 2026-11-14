import { describe, expect, it } from "vitest";
import { safeNext } from "./next-path";

describe("safeNext", () => {
  it("keeps paths on this site", () => {
    expect(safeNext("/o/org_a/audit?before=9")).toBe("/o/org_a/audit?before=9");
  });
  it.each([null, "", "https://evil.example", "//evil.example", "/\\evil.example", "javascript:alert(1)"])(
    "sends %s home",
    (value) => expect(safeNext(value)).toBe("/"),
  );
});
