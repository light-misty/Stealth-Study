import { useTranslation } from "react-i18next";
import { GradingWorkshopBody } from "./GradingWorkshopBody";

export function EssayGradingPanel({ profileId }: { profileId: string }) {
  const { t } = useTranslation();
  return (
    <GradingWorkshopBody
      profileId={profileId}
      kind="essay"
      historySubject="writing"
      title={t("campus.cet.essay.title")}
      desc={t("campus.cet.grading.input_hint")}
      testIdPrefix="campus-cet-essay-grading"
    />
  );
}
