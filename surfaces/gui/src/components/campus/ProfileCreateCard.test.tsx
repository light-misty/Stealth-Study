import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ProfileCreateCard } from "./ProfileCreateCard";

afterEach(cleanup);

const setup = () => {
  const onCreate = vi.fn().mockResolvedValue(undefined);
  const onCancel = vi.fn();
  render(<ProfileCreateCard track="cet" onCreate={onCreate} onCancel={onCancel} />);
  return { onCreate, onCancel };
};

const type = (testId: string, value: string) =>
  fireEvent.change(screen.getByTestId(testId), { target: { value } });

describe("ProfileCreateCard", () => {
  it("submits the filled-in draft", async () => {
    const { onCreate } = setup();
    type("campus-profile-create-title", "英语四级冲刺");
    type("campus-profile-create-exam-date", "2026-12-19");
    type("campus-profile-create-target-score", "500");
    type("campus-profile-create-daily-minutes", "90");

    fireEvent.click(screen.getByTestId("campus-profile-create-submit"));
    expect(onCreate).toHaveBeenCalledWith({
      track_type: "cet",
      title: "英语四级冲刺",
      exam_date: "2026-12-19",
      target_score: 500,
      daily_minutes: 90,
    });
  });

  it("refuses a blank or whitespace-only title and explains why", () => {
    const { onCreate } = setup();
    type("campus-profile-create-title", "   ");
    fireEvent.click(screen.getByTestId("campus-profile-create-submit"));

    expect(onCreate).not.toHaveBeenCalled();
    expect(screen.getByTestId("campus-profile-create-error")).toBeTruthy();
  });

  it("drops empty optional fields instead of sending blanks", () => {
    const { onCreate } = setup();
    type("campus-profile-create-title", "仅填名称");
    fireEvent.click(screen.getByTestId("campus-profile-create-submit"));

    expect(onCreate).toHaveBeenCalledWith({ track_type: "cet", title: "仅填名称" });
  });

  it("turns a non-numeric number field into undefined rather than NaN", () => {
    const { onCreate } = setup();
    type("campus-profile-create-title", "分数乱填");
    type("campus-profile-create-target-score", "abc");
    fireEvent.click(screen.getByTestId("campus-profile-create-submit"));

    expect(onCreate).toHaveBeenCalledWith({ track_type: "cet", title: "分数乱填" });
  });

  it("supports cancelling out of the card", () => {
    const { onCancel } = setup();
    fireEvent.click(screen.getByTestId("campus-profile-create-cancel"));
    expect(onCancel).toHaveBeenCalled();
  });
});
