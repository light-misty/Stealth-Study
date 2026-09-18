import { useTranslation } from "react-i18next";
import { ConnectorsSection } from "./connectors/ConnectorsSection";

// The Connectors surface (renamed from "Integrations", §26). The separate "MCP servers" tab is
// retired (UX-034): custom MCP servers now live on the Connectors page itself — a "Custom · MCP"
// group plus the top "Add custom server" modal. The old "Messaging routing" tab (and its
// ⚠ unrouted badge) moved whole to Inbox ▸ Configure (§28); the one remaining Activity is the
// audit log, reached from the account menu. There is no page sub-nav: with a single section the
// main sidebar is the only left-hand panel.

export function IntegrationsView() {
  const { t: tt } = useTranslation();

  return (
    <main className="flex-1 min-w-0 flex bg-paper">
      <div className="flex-1 min-w-0 overflow-y-auto hairline-scroll">
        <div className="max-w-4xl mx-auto px-7 py-6">
          <section>
            <PanelHead
              title={tt("integrations.connectors_title")}
              sub={tt("integrations.connectors_sub")}
            />
            <ConnectorsSection />
          </section>
        </div>
      </div>
    </main>
  );
}

export function PanelHead({ title, sub }: { title: string; sub: string }) {
  return (
    <div className="mb-4">
      <h2 className="text-[20px] font-semibold tracking-tight">{title}</h2>
      <p className="text-[13px] text-muted mt-0.5">{sub}</p>
    </div>
  );
}
