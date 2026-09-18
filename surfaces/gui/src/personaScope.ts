// A persona is "project-scoped" when it declares requires_folder: an explicit directory the
// user picks, sessions grouped by project in the sidebar. Everything else runs on a transparent
// per-conversation scratch dir, with real folders added as roots when needed — no folder gate.
// (The old family/workspace-enum pair collapsed into this trait; workspace-scratch-design.md.)
export function isProjectScoped(p?: { requires_folder?: boolean }): boolean {
  return p?.requires_folder === true;
}

// Persona naming: the product is "Stealth Study"; the personas are a "study partner" family —
// Study Partner (general), Code Partner, Ops Partner. In lists/chrome we use the SHORT label
// (Study Partner / Code / Ops); the persona detail page uses the FULL family name. Backend names
// are left untouched (the API + tests keep "StealthStudy" / "Ops Coworker"); this is purely the
// display layer.

// Short label for the sidebar + top bar: "Study Partner" / "Code" / "Ops" / "Chat".
export function shortPersonaName(name?: string, id?: string): string {
  if (id === "cowork") return "Study Partner";
  const n = (name || id || "").trim();
  return n.replace(/\s*coworker$/i, "").trim() || n;
}

// Full family name for the persona detail page: "Study Partner" / "Code Partner" / "Ops Partner".
// Chat isn't a partner — left as-is.
export function fullPersonaName(name?: string, id?: string): string {
  if (id === "cowork") return "Study Partner";
  const n = (name || id || "").trim();
  if (id === "chat" || !n) return n;
  return /coworker$/i.test(n) ? n.replace(/coworker$/i, "Partner").trim() : `${n} Partner`;
}
