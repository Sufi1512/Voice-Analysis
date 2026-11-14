import { afterEach, describe, expect, it, vi } from "vitest";
import { api, readCookie } from "./api";
import { initials } from "./initials";

afterEach(() => {
  vi.restoreAllMocks();
  document.cookie = "__Host-nexora_csrf=; Secure; Path=/; max-age=0";
});

describe("readCookie", () => {
  it("finds a cookie among others", () => {
    expect(readCookie("b", "a=1; b=two%20words; c=3")).toBe("two words");
    expect(readCookie("z", "a=1")).toBeNull();
  });
});

describe("api", () => {
  it("sends the CSRF cookie as a header on unsafe methods", async () => {
    document.cookie = "__Host-nexora_csrf=tok123; Secure; Path=/";
    const fetch = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ ok: 1 }), { status: 200 }));
    const r = await api("/v1/auth/login", { method: "POST", json: { email: "a@b.sa" } });
    expect(r).toEqual({ ok: true, status: 200, data: { ok: 1 } });
    const init = fetch.mock.calls[0]![1]!;
    expect((init.headers as Record<string, string>)["X-CSRF-Token"]).toBe("tok123");
    expect(init.credentials).toBe("same-origin");
  });

  it("fetches a CSRF token first when there is none", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      if (String(input) === "/v1/auth/csrf") {
        document.cookie = "__Host-nexora_csrf=fresh; Secure; Path=/";
        return new Response(null, { status: 204 });
      }
      return new Response(null, { status: 204 });
    });
    await api("/v1/auth/logout", { method: "POST" });
    expect(fetch.mock.calls.map((c) => String(c[0]))).toEqual(["/v1/auth/csrf", "/v1/auth/logout"]);
    expect((fetch.mock.calls[1]![1]!.headers as Record<string, string>)["X-CSRF-Token"]).toBe("fresh");
  });

  it("does not send a CSRF header on GET", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("{}", { status: 200 }));
    await api("/v1/me");
    expect((fetch.mock.calls[0]![1]!.headers as Record<string, string>)["X-CSRF-Token"]).toBeUndefined();
  });

  it("returns Core's error code, or a generic one", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(JSON.stringify({ error: "locked" }), { status: 429 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ detail: [] }), { status: 422 }))
      .mockResolvedValueOnce(new Response("oops", { status: 500 }));
    expect(await api("/x")).toMatchObject({ ok: false, status: 429, error: "locked" });
    expect(await api("/x")).toMatchObject({ ok: false, status: 422, error: "invalid_input" });
    expect(await api("/x")).toMatchObject({ ok: false, status: 500, error: "unexpected" });
  });

  it("reports network failures without throwing", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("offline"));
    expect(await api("/x")).toMatchObject({ ok: false, status: 0, error: "network" });
  });
});

describe("initials", () => {
  it("uses first and last name, one name, or the email", () => {
    expect(initials("Noura Al Saud", "n@x.sa")).toBe("NS");
    expect(initials("Sara", "s@x.sa")).toBe("SA");
    expect(initials("", "khalid@x.sa")).toBe("KH");
  });
});
