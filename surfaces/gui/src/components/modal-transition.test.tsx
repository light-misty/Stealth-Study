import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render } from "@testing-library/react";
import { fireEvent } from "@testing-library/react";

vi.mock("../api", () => ({
  cloudLogin: vi.fn(),
  connectManaged: vi.fn(),
  getCloudStatus: vi.fn().mockResolvedValue({ signed_in: false, account: null }),
  getConnectors: vi.fn().mockResolvedValue([]),
  setOnboarded: vi.fn(),
}));

vi.mock("../connectors/ConnectorIcon", () => ({
  ConnectorBadge: () => <span />,
}));

vi.mock("../providers/ProviderSetup", () => ({
  ProviderCards: () => <div />,
  ProviderForm: () => <div />,
  useProviderSetup: () => ({
    phase: "pick",
    providers: [],
    active: null,
    error: null,
    busy: null,
    downloadProgress: null,
    keylessOk: new Set(),
    sel: null,
    dirty: false,
    secretFilled: false,
    verify: { state: "idle" },
    onPick: vi.fn(),
    onBack: vi.fn(),
    onSubmit: vi.fn(),
  }),
}));

vi.mock("../tauri", () => ({
  checkForUpdate: vi.fn().mockResolvedValue({ version: "1.2.0", notes: "" }),
  clearPendingUpdate: vi.fn(),
  downloadUpdate: vi.fn(),
  installUpdate: vi.fn(),
  isTauri: () => true,
}));

import { Onboarding } from "./Onboarding";
import { SearchModal } from "./SearchModal";
import { SelectMenu } from "./SelectMenu";
import { UpdateBanner } from "./UpdateBanner";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("modal overlays carry entrance transitions", () => {
  it("Onboarding fades its scrim and pops its card", () => {
    const { getByTestId } = render(<Onboarding onDone={vi.fn()} />);
    const root = getByTestId("onboarding");
    expect(root.classList.contains("overlay-fade")).toBe(true);
    expect(root.firstElementChild?.classList.contains("card-pop")).toBe(true);
  });

  it("SearchModal fades its scrim and pops its panel", () => {
    const { container } = render(
      <SearchModal sessions={[]} onClose={vi.fn()} onSelect={vi.fn()} />,
    );
    const root = container.firstElementChild as HTMLElement;
    expect(root.classList.contains("overlay-fade")).toBe(true);
    expect(root.querySelector(".modal-pop")).not.toBeNull();
  });

  it("SelectMenu pops its listbox", () => {
    const { getByLabelText, getByRole } = render(
      <SelectMenu
        value="a"
        options={[{ value: "a", label: "Alpha" }]}
        onChange={vi.fn()}
        ariaLabel="pick"
      />,
    );
    fireEvent.click(getByLabelText("pick"));
    expect(getByRole("listbox").classList.contains("menu-pop")).toBe(true);
  });

  it("UpdateBanner slides in when an update is found", async () => {
    vi.useFakeTimers();
    const { container } = render(<UpdateBanner />);
    await act(() => vi.advanceTimersByTimeAsync(15_000));
    expect(container.firstElementChild?.classList.contains("anim-fade-up")).toBe(true);
  });
});
