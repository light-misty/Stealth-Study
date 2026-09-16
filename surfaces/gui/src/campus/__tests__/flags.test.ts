import { afterEach, describe, expect, it } from "vitest";
import { showVoice, showLogin } from "../../flags";

describe("campus station flag behaviour", () => {
  afterEach(() => {
    localStorage.removeItem("ocw.flag.voice");
    localStorage.removeItem("ocw.flag.login");
  });

  it("keeps the voice entry off by default so no mic permission is requested in campus views", () => {
    expect(showVoice()).toBe(false);
  });

  it("keeps the login entry off by default so campus views never render cloud sign-in", () => {
    expect(showLogin()).toBe(false);
  });

  it("restores the voice affordance when the flag is flipped to 1", () => {
    localStorage.setItem("ocw.flag.voice", "1");
    expect(showVoice()).toBe(true);
  });

  it("restores the login affordance when the flag is flipped to 1", () => {
    localStorage.setItem("ocw.flag.login", "1");
    expect(showLogin()).toBe(true);
  });

  it("force-hides both entry points when set to 0 (deterministic default-override)", () => {
    localStorage.setItem("ocw.flag.voice", "0");
    localStorage.setItem("ocw.flag.login", "0");
    expect(showVoice()).toBe(false);
    expect(showLogin()).toBe(false);
  });
});
