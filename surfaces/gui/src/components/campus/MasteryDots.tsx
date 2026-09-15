import { useTranslation } from "react-i18next";
import { MASTERY_LEVELS, type MasteryLevel } from "../../campus/types";

// Mastery is shown as dots PLUS a word: PRD §7.4 forbids colour as the only carrier of
// meaning, so the level is always spelled out next to the dots.

const DOT: Record<MasteryLevel, string> = {
  unknown: "bg-transparent border border-line",
  fuzzy: "bg-warnInk",
  mastered: "bg-ok",
};

export function MasteryDots({
  level,
  size = "md",
}: {
  level: MasteryLevel;
  size?: "sm" | "md";
}) {
  const { t } = useTranslation();
  const label = t(`campus.common.mastery.${level}`);
  const box = size === "sm" ? "h-1.5 w-1.5" : "h-2 w-2";

  return (
    <span
      className="inline-flex items-center gap-1.5"
      data-testid="campus-mastery-dots"
      data-level={level}
      aria-label={label}
      title={label}
    >
      {MASTERY_LEVELS.map((candidate) => (
        <span
          key={candidate}
          className={`${box} rounded-full ${candidate === level ? DOT[candidate] : "bg-transparent border border-line"}`}
          data-testid="campus-mastery-dot"
          data-level={candidate}
          data-on={candidate === level ? "true" : "false"}
        />
      ))}
      <span className="text-[11px] text-muted" data-testid="campus-mastery-label">
        {label}
      </span>
    </span>
  );
}
