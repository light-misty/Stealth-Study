import { useTranslation } from "react-i18next";
import { useProfileImpact } from "../../campus/hooks";
import type { ExamProfile } from "../../campus/types";
import {
  campusErrorInfo,
  campusErrorKey,
  profileImpactRows,
  profileImpactTotal,
} from "../../campus/utils";
import { Icon } from "../Icon";
import { CampusDialog } from "./CampusDialog";

interface Props {
  profile: ExamProfile;
  busy: boolean;
  error: unknown;
  onConfirm: (profileId: string) => void;
  onClose: () => void;
}

export function DeleteProfileDialog({ profile, busy, error, onConfirm, onClose }: Props) {
  const { t } = useTranslation();
  const { impact, loading, error: impactError } = useProfileImpact(profile.id);
  const rows = profileImpactRows(impact);
  const total = profileImpactTotal(impact);
  const info = error ? campusErrorInfo(error) : null;
  const counting = loading && !impactError;

  return (
    <CampusDialog
      testId="campus-delete-dialog"
      title={t("campus.delete.title")}
      icon="trash"
      onClose={onClose}
      footer={
        <>
          <button
            type="button"
            className="btn btn--ghost"
            onClick={onClose}
            data-testid="campus-delete-cancel"
          >
            {t("campus.profile.create_cancel")}
          </button>
          <button
            type="button"
            className="btn btn--danger is-solid"
            onClick={() => onConfirm(profile.id)}
            disabled={busy || counting}
            data-testid="campus-delete-confirm"
          >
            {t("campus.delete.confirm")}
          </button>
        </>
      }
    >
      <div className="stack-gap">
        <p className="dlg-lead">{t("campus.delete.lead", { title: profile.title })}</p>

        <div className="kv kv--wide" data-testid="campus-delete-rows">
          {rows.map((row) => (
            <div className="kv-row" key={row.key}>
              <span className="kv-k">{t(`campus.delete.group.${row.key}`)}</span>
              <span className="kv-v num" data-testid="campus-delete-row" data-key={row.key}>
                {row.count}
              </span>
            </div>
          ))}
        </div>

        {counting ? (
          <p className="dlg-note" data-testid="campus-delete-loading">
            {t("campus.common.loading")}
          </p>
        ) : null}
        {impactError && !loading ? (
          <p className="dlg-note" data-testid="campus-delete-unavailable">
            {t("campus.delete.unavailable")}
          </p>
        ) : null}
        {!rows.length && !counting && !impactError ? (
          <p className="dlg-note">{t("campus.delete.none")}</p>
        ) : null}

        <p className="dlg-note" data-testid="campus-delete-count" data-total={total ?? ""}>
          {total == null
            ? t("campus.delete.total_unknown")
            : t("campus.delete.total", { count: total })}
        </p>

        <div className="alert alert--danger">
          <Icon name="warning" size={14} />
          <div className="alert-text">
            <span className="alert-title">{t("campus.delete.irreversible")}</span>
            <span className="alert-desc">
              {t(
                profile.status === "finished"
                  ? "campus.delete.finished_note"
                  : "campus.delete.archived_note",
              )}
            </span>
          </div>
        </div>

        {info ? (
          <div className="flex items-center gap-2 text-[12px] text-warnInk" data-testid="campus-delete-error">
            <span className="min-w-0">
              {t(campusErrorKey(info.code), { defaultValue: info.message || t("campus.common.error") })}
            </span>
            <button
              type="button"
              className="btn btn--ghost btn--sm"
              onClick={() => onConfirm(profile.id)}
              data-testid="campus-delete-retry"
            >
              {t("campus.common.retry")}
            </button>
          </div>
        ) : null}
      </div>
    </CampusDialog>
  );
}
