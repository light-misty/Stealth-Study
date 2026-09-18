import { afterEach, describe, expect, it } from "vitest";
import { installContextMenuGuard, shouldBeginWindowDrag } from "./desktopChrome";

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

describe("shouldBeginWindowDrag", () => {
  const region = document.createElement("div");
  const label = document.createElement("span");
  const button = document.createElement("button");
  const glyph = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  button.appendChild(glyph);
  const input = document.createElement("input");
  const link = document.createElement("a");
  const exempt = document.createElement("div");
  exempt.setAttribute("data-no-drag", "");
  const exemptInner = document.createElement("em");
  exempt.appendChild(exemptInner);
  region.append(label, button, input, link, exempt);

  it("drags the window from the bare surfaces of a drag region", () => {
    expect(shouldBeginWindowDrag(region)).toBe(true);
    expect(shouldBeginWindowDrag(label)).toBe(true);
  });

  it("never drags from a control, its glyph, or a data-no-drag subtree", () => {
    for (const target of [button, glyph, input, link, exempt, exemptInner]) {
      expect(shouldBeginWindowDrag(target), target.tagName).toBe(false);
    }
  });
});
