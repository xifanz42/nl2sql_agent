export type ChatKind =
  | "sql"
  | "clarification"
  | "refuse"
  | "exploration"
  | "invalid"
  | "execution_error"
  | "store_error"
  | "too_many_rows";

export interface ChatResult {
  kind: ChatKind;
  sql: string;
  rows: Record<string, unknown>[];
  analysis: string;
  message: string;
  execution_time_ms: number;
  processing_time_ms: number;
  prompt_tokens: number;
  completion_tokens: number;
  cached_tokens: number;
  calls: number;
  cost_cny: number;
  unpriced_models: string[];
  total_rows: number;
  truncated: boolean;
}

export interface ChatResponse {
  session_id: string;
  result: ChatResult;
}

export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

const SESSION_KEY = "nl2sql.session_id";
const NIL_UUID = "00000000-0000-0000-0000-000000000000";
const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

// Keeps the session alive for this page even when storage is disabled.
let memorySessionId: string | null = null;

function readStoredSession(): string | null {
  try {
    const stored = localStorage.getItem(SESSION_KEY);
    if (stored) {
      memorySessionId = stored;
      return stored;
    }
  } catch {
    // Fall through to the in-memory value.
  }
  return memorySessionId;
}

function writeStoredSession(sessionId: string): void {
  memorySessionId = sessionId;
  try {
    localStorage.setItem(SESSION_KEY, sessionId);
  } catch {
    // Storage can be unavailable (private mode); the in-memory value still works.
  }
}

export function randomUuid(): string {
  if (typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0"));
  return [
    hex.slice(0, 4).join(""),
    hex.slice(4, 6).join(""),
    hex.slice(6, 8).join(""),
    hex.slice(8, 10).join(""),
    hex.slice(10).join(""),
  ].join("-");
}

export function storeSessionId(sessionId: string): void {
  writeStoredSession(sessionId);
}

export function newSessionId(): string {
  const sessionId = randomUuid();
  writeStoredSession(sessionId);
  return sessionId;
}

export function currentSessionId(): string {
  const stored = readStoredSession();
  if (stored && UUID_RE.test(stored) && stored.toLowerCase() !== NIL_UUID) {
    return stored;
  }
  return newSessionId();
}

interface ParsedBody {
  json: unknown;
  detail: string | null;
}

function detailMessage(value: unknown): string | null {
  if (typeof value === "string") {
    return value;
  }
  if (Array.isArray(value) && value.length > 0) {
    const first = value[0] as { msg?: unknown };
    if (first && typeof first === "object" && typeof first.msg === "string") {
      return first.msg;
    }
  }
  return null;
}

async function readBody(response: Response): Promise<ParsedBody> {
  const text = await response.text();
  if (!text) {
    return { json: null, detail: null };
  }
  try {
    const json: unknown = JSON.parse(text);
    if (json && typeof json === "object" && "detail" in json) {
      return { json, detail: detailMessage((json as { detail: unknown }).detail) };
    }
    return { json, detail: null };
  } catch {
    return { json: null, detail: text };
  }
}

export async function postChat(message: string): Promise<ChatResponse> {
  const response = await fetch("/api/v1/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, session_id: currentSessionId() }),
  });
  const body = await readBody(response);
  const payload = body.json as Partial<ChatResponse> | null;
  const fallback = body.detail ?? "";

  if (payload?.result && payload.session_id) {
    writeStoredSession(payload.session_id);
    if (response.status !== 200 && response.status !== 503) {
      throw new ApiError(payload.result.message || fallback, response.status);
    }
    return { session_id: payload.session_id, result: payload.result };
  }
  throw new ApiError(fallback, response.status);
}

// The server enforces this limit; mirror it so long input fails in the UI first.
export async function getMaxMessageChars(): Promise<number | null> {
  try {
    const response = await fetch("/api/v1/config");
    if (!response.ok) {
      return null;
    }
    const body = await readBody(response);
    const payload = body.json as { max_message_chars?: unknown } | null;
    return payload && typeof payload.max_message_chars === "number"
      ? payload.max_message_chars
      : null;
  } catch {
    return null;
  }
}

// Kept in sync with SUPPORTED_DOCUMENT_EXTENSIONS in document_processor.py.
export const UPLOAD_ACCEPT = [
  ".txt",
  ".log",
  ".md",
  ".markdown",
  ".csv",
  ".json",
  ".jsonl",
  ".yaml",
  ".yml",
  ".xml",
  ".html",
  ".htm",
  ".sql",
  ".py",
  ".js",
  ".ts",
  ".java",
  ".go",
  ".rs",
  ".sh",
  ".pdf",
  ".docx",
  ".xlsx",
  ".pptx",
  ".rtf",
  ".odt",
  ".ods",
  ".epub",
].join(",");

// Returns the original upload name; the UI owns the display text.
export async function uploadDocument(file: File): Promise<string | null> {
  const form = new FormData();
  form.append("file", file);
  const response = await fetch("/api/v1/documents", {
    method: "POST",
    body: form,
  });
  const body = await readBody(response);
  if (!response.ok) {
    throw new ApiError(body.detail ?? "", response.status);
  }
  const payload = body.json as { filename?: unknown } | null;
  return payload && typeof payload.filename === "string" ? payload.filename : null;
}
