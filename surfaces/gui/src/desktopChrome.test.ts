import { afterEach, describe, expect, it } from "vitest";
import { installContextMenuGuard } from "./desktopChrome";

describe("installContextMenuGuard", () => {
  let dispose: (() => void) | null = null;
  afterEach(() => {
    dispose?.();
    dispose = null;
  });

  const rightClick = (node: Element) => {
    const event = new MouseEvent("contextmenu", { bubbles: true, cancelable: true });
    node.dispatchEvent(event);
    return event.defaultPrevented;
  };

  it("blocks the native context menu on every surface of the app", () => {
    const aside = document.createElement("aside");
    const inner = document.createElement("span");
    aside.appendChild(inner);
    document.body.appendChild(aside);
    const textarea = document.createElement("textarea");
    document.body.appendChild(textarea);

    dispose = installContextMenuGuard();

    expect(rightClick(document.body)).toBe(true);
    expect(rightClick(inner)).toBe(true);
    expect(rightClick(textarea)).toBe(true);
  });

  it("stops blocking once disposed", () => {
    dispose = installContextMenuGuard();
    dispose();
    dispose = null;
    expect(rightClick(document.body)).toBe(false);
  });
});
