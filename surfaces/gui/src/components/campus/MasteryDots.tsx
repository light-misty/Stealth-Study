import { useTranslation } from "react-i18next";
import { MASTERY_LEVELS, type MasteryLevel } from "../../campus/types";

// Mastery is shown as dots PLUS a word: PRD §7.4 forbids colour as the only carrier of
// meaning, so the level is always spelled out next to the dots.

export function MasteryDots({
  level,
  size = "md",
}: {
  level: MasteryLevel;
  size?: "sm" | "md";
}) {
  const { t } = useTranslation();
  const label = t(`campus.common.mastery.${level}`);

  return (
    <span
      className={size === "sm" ? "mas mas--sm" : "mas"}
      data-testid="campus-mastery-dots"
      data-level={level}
      aria-label={label}
      title={label}
    >
      <span className="mas-dots">
        {MASTERY_LEVELS.map((candidate) => (
          <span
            key={candidate}
            className={
              candidate === level
                ? `mas-dot mas-dot--${candidate} is-on`
                : `mas-dot mas-dot--${candidate}`
            }
            data-testid="campus-mastery-dot"
            data-level={candidate}
            data-on={candidate === level ? "true" : "false"}
          />
        ))}
      </span>
      <span className="mas-l" data-testid="campus-mastery-label">
        {label}
      </span>
    </span>
  );
}
