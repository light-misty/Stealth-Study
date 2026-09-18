// A persona is "project-scoped" when it declares requires_folder: an explicit directory the
// user picks, sessions grouped by project in the sidebar. Everything else runs on a transparent
// per-conversation scratch dir, with real folders added as roots when needed — no folder gate.
// (The old family/workspace-enum pair collapsed into this trait; workspace-scratch-design.md.)
import i18n from "i18next";

export function isProjectScoped(p?: { requires_folder?: boolean }): boolean {
  return p?.requires_folder === true;
}

// Persona naming: the personas are a "study partner" family. In lists/chrome we use the SHORT
// label (Study Partner / Code / Ops); the persona detail page uses the FULL name. Backend names
// are left untouched (the API keeps "StealthStudy" / "Ops Coworker"); this is the display layer,
// and the family word comes from the locale so the Chinese UI never shows an English label.

// Short label for the sidebar + top bar: "Study Partner" / "Code" / "Ops" / "Chat".
export function shortPersonaName(name?: string, id?: string): string {
  if (id === "cowork") return i18n.t("persona.partner_label");
  const n = (name || id || "").trim();
  return n.replace(/\s*coworker$/i, "").trim() || n;
}

// Full display name for the persona detail page + the composer's partner chip.
// Chat isn't a partner — left as-is.
export function fullPersonaName(name?: string, id?: string): string {
  if (id === "cowork") return i18n.t("persona.partner_label");
  const n = (name || id || "").trim();
  if (id === "chat" || !n) return n;
  const base = n.replace(/\s*coworker$/i, "").trim() || n;
  return i18n.t("persona.partner_named", { name: base });
}
