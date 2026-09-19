import { useTranslation } from "react-i18next";
import { GradingWorkshopBody } from "./GradingWorkshopBody";

export function TranslationGradingPanel({ profileId }: { profileId: string }) {
  const { t } = useTranslation();
  return (
    <GradingWorkshopBody
      profileId={profileId}
      kind="translation"
      historySubject="translation"
      title={t("campus.cet.translation.title")}
      desc={t("campus.cet.translation.hint")}
      icon="globe"
      testIdPrefix="campus-cet-translation-grading"
    />
  );
}
