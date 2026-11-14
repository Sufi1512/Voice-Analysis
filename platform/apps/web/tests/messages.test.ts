// next-intl reads "." in a key as nesting, so a dotted key silently renders as its raw path.
import { describe, expect, it } from "vitest";
import messages from "../messages/en.json";
import { KNOWN_ACTIONS, actionKey } from "../src/components/org/actions";

function keys(obj: object, path: string[] = []): string[][] {
  return Object.entries(obj).flatMap(([k, v]) => (v && typeof v === "object" ? keys(v, [...path, k]) : [[...path, k]]));
}

describe("messages/en.json", () => {
  it("has no dots inside keys", () => {
    for (const path of keys(messages)) for (const part of path) expect(part, path.join(" > ")).not.toContain(".");
  });
  it("has wording for every known audit action", () => {
    for (const action of KNOWN_ACTIONS) expect(messages.audit.actions[actionKey(action)], action).toBeTruthy();
  });
});
