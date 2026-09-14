import { afterEach, describe, expect, it } from "vitest";
import { showLogin } from "./flags";

describe("showLogin", () => {
  afterEach(() => {
    localStorage.removeItem("ocw.flag.login");
  });

  it("ships OFF so no sign-in affordance renders by default", () => {
    expect(showLogin()).toBe(false);
  });

  it("is re-enabled by ocw.flag.login = 1 (reversibility)", () => {
    localStorage.setItem("ocw.flag.login", "1");
    expect(showLogin()).toBe(true);
  });

  it("is force-hidden by ocw.flag.login = 0", () => {
    localStorage.setItem("ocw.flag.login", "0");
    expect(showLogin()).toBe(false);
  });

  it("falls back to the shipped default on an unrecognised value", () => {
    localStorage.setItem("ocw.flag.login", "yes");
    expect(showLogin()).toBe(false);
  });
});
