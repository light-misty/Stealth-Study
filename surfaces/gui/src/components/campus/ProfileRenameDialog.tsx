import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { ExamProfile } from "../../campus/types";
import { profileTitleTaken } from "../../campus/utils";
import { CampusDialog } from "./CampusDialog";

interface Props {
  profile: ExamProfile;
  profiles: ExamProfile[];
  onSubmit: (title: string) => Promise<boolean>;
  onClose: () => void;
}

export function ProfileRenameDialog({ profile, profiles, onSubmit, onClose }: Props) {
  const { t } = useTranslation();
  const [title, setTitle] = useState(profile.title);
  const [busy, setBusy] = useState(false);
  const [refused, setRefused] = useState(false);
  const clean = title.trim();
  const taken =
    (clean !== "" &&
      clean !== profile.title &&
      profileTitleTaken(profiles, clean, profile.id)) ||
    refused;
  const invalid = clean === "" || taken;

  const save = async () => {
    if (busy || invalid) return;
    setBusy(true);
    setRefused(false);
    const ok = await onSubmit(clean);
    setBusy(false);
    if (ok) {
      onClose();
      return;
    }
    setRefused(true);
  };

  return (
    <CampusDialog
      testId="campus-profile-rename"
      title={t("campus.profile.rename_title")}
      onClose={onClose}
      footer={
        <>
          <button
            type="button"
            className="btn btn--text"
            onClick={onClose}
            data-testid="campus-profile-rename-cancel"
          >
            {t("campus.profile.create_cancel")}
          </button>
          <button
            type="button"
            className="btn btn--primary"
            onClick={() => void save()}
            disabled={busy || invalid}
            data-testid="campus-profile-rename-save"
          >
            {t("campus.profile.rename_save")}
          </button>
        </>
      }
    >
      <div className={invalid ? "field is-bad" : "field"}>
        <span className="field-label">{t("campus.profile.title_label")}</span>
        <input
          className="input"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          data-testid="campus-profile-rename-input"
        />
        {clean === "" ? (
          <span className="field-err" data-testid="campus-profile-rename-error">
            {t("campus.profile.title_required")}
          </span>
        ) : taken ? (
          <span className="field-err" data-testid="campus-profile-rename-error">
            {t("campus.error.duplicate_title")}
          </span>
        ) : null}
      </div>
    </CampusDialog>
  );
}
