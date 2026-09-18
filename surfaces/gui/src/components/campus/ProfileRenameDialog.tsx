import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { ExamProfile } from "../../campus/types";
import { profileTitleTaken } from "../../campus/utils";
import { CampusDialog } from "./CampusDialog";

const FIELD =
  "w-full rounded-lg border border-line bg-transparent px-2.5 py-1.5 text-[13px] text-ink outline-none";

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
      width="w-[400px]"
      footer={
        <>
          <button
            type="button"
            className="px-2.5 py-1.5 text-[13px] text-faint hover:text-muted"
            onClick={onClose}
            data-testid="campus-profile-rename-cancel"
          >
            {t("campus.profile.create_cancel")}
          </button>
          <button
            type="button"
            className="px-3 py-1.5 rounded-lg bg-accent text-white text-[13px] disabled:opacity-40"
            onClick={() => void save()}
            disabled={busy || invalid}
            data-testid="campus-profile-rename-save"
          >
            {t("campus.profile.rename_save")}
          </button>
        </>
      }
    >
      <label className="block">
        <span className="text-[12px] text-muted">{t("campus.profile.title_label")}</span>
        <input
          className={`${FIELD} mt-1`}
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          data-testid="campus-profile-rename-input"
        />
      </label>
      {clean === "" ? (
        <div className="mt-2 text-[12px] text-warnInk" data-testid="campus-profile-rename-error">
          {t("campus.profile.title_required")}
        </div>
      ) : taken ? (
        <div className="mt-2 text-[12px] text-warnInk" data-testid="campus-profile-rename-error">
          {t("campus.error.duplicate_title")}
        </div>
      ) : null}
    </CampusDialog>
  );
}
