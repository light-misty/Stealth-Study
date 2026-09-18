export function installContextMenuGuard(): () => void {
  const block = (event: Event) => event.preventDefault();
  window.addEventListener("contextmenu", block, true);
  return () => window.removeEventListener("contextmenu", block, true);
}
