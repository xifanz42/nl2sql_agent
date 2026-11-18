export type Lang = "zh" | "en";

export interface Messages {
  brandSub: string;
  sessions: string;
  upload: string;
  newConversation: string;
  sessionChip: (shortId: string) => string;
  emptyTitle: string;
  emptyBody: string;
  placeholder: string;
  send: string;
  sending: string;
  composerHint: string;
  thinking: string;
  requestFailed: string;
  networkError: string;
  uploadPending: (name: string) => string;
  uploadFailed: string;
  dataCard: string;
  rowUnit: (count: number) => string;
  copy: string;
  copied: string;
  queryDone: string;
  noRows: string;
  truncatedNote: (count: number) => string;
  tooManyNote: (count: number) => string;
  executionFailed: string;
  invalid: string;
  storeError: string;
  idleHint: (tokens: string, calls: number, cost: string) => string;
  noSessions: string;
  close: string;
  untitled: string;
  language: string;
}

const zh: Messages = {
  brandSub: "用自然语言问数据",
  sessions: "会话",
  upload: "上传文档",
  newConversation: "新对话",
  sessionChip: (shortId) => `会话 ${shortId}`,
  emptyTitle: "问你的数据。",
  emptyBody: "用中文或英文提问。分析直接呈现，具体数据按需展开。",
  placeholder: "问一个关于数据的问题…",
  send: "发送",
  sending: "查询中…",
  composerHint: "Enter 发送 · Shift + Enter 换行",
  thinking: "正在查询…",
  requestFailed: "请求失败",
  networkError: "请求失败，请确认 API 服务已启动。",
  uploadPending: (name) => `正在上传 ${name}…`,
  uploadFailed: "上传失败，请稍后重试。",
  dataCard: "点击查看具体数据",
  rowUnit: (count) => `${count} 行`,
  copy: "复制",
  copied: "已复制",
  queryDone: "查询已完成。",
  noRows: "查询未返回数据。",
  truncatedNote: (count) => `返回行数超过上限，结果仅保留前 ${count} 行。`,
  tooManyNote: (count) =>
    `仅预览前 ${count} 行。请缩小时间范围或补充过滤条件后重试。`,
  executionFailed: "执行失败",
  invalid: "请求无效",
  storeError: "会话不可用",
  idleHint: (tokens, calls, cost) =>
    `本次会话累计 ${tokens} tokens · ${calls} 次调用 · 费用 ${cost}`,
  noSessions: "还没有历史会话。",
  close: "关闭",
  untitled: "未命名会话",
  language: "语言",
};

const en: Messages = {
  brandSub: "Ask your data",
  sessions: "Chats",
  upload: "Upload",
  newConversation: "New chat",
  sessionChip: (shortId) => `Session ${shortId}`,
  emptyTitle: "Ask your data.",
  emptyBody:
    "Ask in Chinese or English. The analysis appears first; the underlying data opens on demand.",
  placeholder: "Ask a question about your data…",
  send: "Send",
  sending: "Querying…",
  composerHint: "Enter to send · Shift + Enter for a new line",
  thinking: "Querying…",
  requestFailed: "Request failed",
  networkError: "Request failed. Check that the API is running.",
  uploadPending: (name) => `Uploading ${name}…`,
  uploadFailed: "Upload failed. Try again.",
  dataCard: "View the data",
  rowUnit: (count) => `${count} ${count === 1 ? "row" : "rows"}`,
  copy: "Copy",
  copied: "Copied",
  queryDone: "Query completed.",
  noRows: "The query returned no rows.",
  truncatedNote: (count) =>
    `Result exceeded the row limit; only the first ${count} rows are shown.`,
  tooManyNote: (count) =>
    `Previewing the first ${count} rows. Narrow the date range or add filters and retry.`,
  executionFailed: "Execution failed",
  invalid: "Invalid request",
  storeError: "Session unavailable",
  idleHint: (tokens, calls, cost) =>
    `This session: ${tokens} tokens · ${calls} calls · ${cost}`,
  noSessions: "No saved chats yet.",
  close: "Close",
  untitled: "Untitled chat",
  language: "Language",
};

export const MESSAGES: Record<Lang, Messages> = { zh, en };

const LANG_KEY = "nl2sql.lang";

export function detectLang(): Lang {
  try {
    const stored = localStorage.getItem(LANG_KEY);
    if (stored === "zh" || stored === "en") {
      return stored;
    }
  } catch {
    // Ignore storage failures and fall back to the browser language.
  }
  return navigator.language.toLowerCase().startsWith("zh") ? "zh" : "en";
}

export function storeLang(lang: Lang): void {
  try {
    localStorage.setItem(LANG_KEY, lang);
  } catch {
    // Language still applies for this page view.
  }
}

export function localeOf(lang: Lang): string {
  return lang === "zh" ? "zh-CN" : "en-US";
}
