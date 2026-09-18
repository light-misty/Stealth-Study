const DRAG_EXEMPT = "button, a, input, textarea, select, [data-no-drag]";

export function installContextMenuGuard(): () => void {
  const block = (event: Event) => event.preventDefault();
  window.addEventListener("contextmenu", block, true);
  return () => window.removeEventListener("contextmenu", block, true);
}

export function shouldBeginWindowDrag(target: EventTarget | null): boolean {
  return !(target instanceof Element) || target.closest(DRAG_EXEMPT) === null;
}
