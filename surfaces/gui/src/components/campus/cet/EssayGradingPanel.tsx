import { useTranslation } from "react-i18next";
import { GradingWorkshopBody } from "./GradingWorkshopBody";

export function EssayGradingPanel({ profileId }: { profileId: string }) {
  const { t } = useTranslation();
  return (
    <div className="grid gap-3">
      <div className="text-[13px] font-semibold text-ink">{t("campus.cet.essay.title")}</div>
      <GradingWorkshopBody
        profileId={profileId}
        kind="essay"
        historySubject="writing"
        testIdPrefix="campus-cet-essay-grading"
      />
    </div>
  );
}
