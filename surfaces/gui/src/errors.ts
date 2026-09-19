/** 后端错误响应的最小公共形状：`error` 是原始文本，`error_code` 是稳定代号。 */
export interface ErrorBearing {
  error?: string | null;
  error_code?: string | null;
}

export type Translate = (key: string, options?: Record<string, unknown>) => string;

/** 原始后端文本 —— 供悬浮提示、详情区与日志使用，永远不参与翻译。 */
export function apiErrorDetail(res?: ErrorBearing | null): string {
  return res?.error ?? "";
}

function normalizeCode(code?: string | null): string {
  return (code || "").trim().toLowerCase().replace(/[^a-z0-9_]/g, "");
}

/**
 * 界面该显示的那句话：代号在语言包里有 `error.<code>` 就用它，否则退回后端原文，
 * 两者皆空时给通用提示。`fallback` 用于调用方已有的本地兜底文案。
 */
export function apiErrorText(
  res: ErrorBearing | null | undefined,
  t: Translate,
  fallback = "",
): string {
  const raw = apiErrorDetail(res);
  const code = normalizeCode(res?.error_code);
  const nothing = raw || fallback || t("error.unclassified");
  if (!code) return nothing;
  return t(`error.${code}`, { defaultValue: nothing });
}
