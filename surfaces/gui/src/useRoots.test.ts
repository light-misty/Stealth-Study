import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useRoots } from "./useRoots";

type Route = { match: string; method?: string; json: unknown };

function stub(routes: Route[]) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = (init?.method || "GET").toUpperCase();
      for (const r of routes) {
        if (String(url).includes(r.match) && (!r.method || r.method === method)) {
          return { ok: true, json: async () => r.json } as Response;
        }
      }
      return { ok: true, json: async () => ({}) } as Response;
    }),
  );
}

const EMPTY_LIST = { match: "/v1/sessions/s1/roots", method: "GET", json: { roots: [] } };

describe("useRoots 的错误出口", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("有代号时界面文案取语言包，后端原文留在 errorDetail", async () => {
    stub([
      EMPTY_LIST,
      {
        match: "/v1/sessions/s1/roots",
        method: "POST",
        json: { ok: false, error: "not a directory: /tmp/x", error_code: "NOT_A_DIRECTORY" },
      },
    ]);
    const { result } = renderHook(() => useRoots("s1"));
    await waitFor(() => expect(result.current.roots).toEqual([]));
    await act(async () => {
      await result.current.addRoot("/tmp/x", false);
    });
    expect(result.current.error).toBe("That path isn't a folder.");
    expect(result.current.errorDetail).toBe("not a directory: /tmp/x");
  });

  it("没有代号时退回后端原文，不编造提示", async () => {
    stub([
      EMPTY_LIST,
      {
        match: "/v1/sessions/s1/roots",
        method: "POST",
        json: { ok: false, error: "a sentence no code exists for" },
      },
    ]);
    const { result } = renderHook(() => useRoots("s1"));
    await waitFor(() => expect(result.current.roots).toEqual([]));
    await act(async () => {
      await result.current.addRoot("/tmp/x", false);
    });
    expect(result.current.error).toBe("a sentence no code exists for");
  });
});
