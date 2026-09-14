import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";

vi.mock("../api", () => ({
  cloudLogin: vi.fn(),
  getCloudGallery: vi.fn().mockResolvedValue({ ok: true, personas: [] }),
  getCloudGalleryDetail: vi.fn(),
  getCloudStatus: vi.fn().mockResolvedValue({ signed_in: false, account: "", user_id: "" }),
  getPersonas: vi.fn().mockResolvedValue({ personas: [] }),
  installPersona: vi.fn(),
}));

vi.mock("./PersonaHero", () => ({
  PersonaHero: () => <div />,
}));

import { GalleryModal } from "./GalleryModal";

afterEach(() => {
  cleanup();
  localStorage.removeItem("ocw.flag.login");
});

describe("GalleryModal sign-in card (G-06)", () => {
  it("never shows the sign-in card while the flag is off", async () => {
    render(<GalleryModal onClose={vi.fn()} />);
    await screen.findByTestId("gallery-modal");
    await waitFor(() => expect(screen.queryByTestId("gallery-loading")).toBeNull());
    expect(screen.queryByTestId("gallery-signin")).toBeNull();
  });

  it("shows the sign-in card again when the flag is on", async () => {
    localStorage.setItem("ocw.flag.login", "1");
    render(<GalleryModal onClose={vi.fn()} />);
    await screen.findByTestId("gallery-modal");
    await waitFor(() => expect(screen.getByTestId("gallery-signin")).toBeTruthy());
  });
});
