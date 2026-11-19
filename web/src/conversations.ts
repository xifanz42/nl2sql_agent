import type { ChatResult } from "./api";

export interface Exchange {
  id: string;
  question: string;
  result?: ChatResult;
  error?: string;
  // Rows are never persisted; a restored turn keeps its analysis/SQL and
  // shows this flag instead of claiming the query returned no data.
  resultsUnavailable?: boolean;
}

export interface StoredConversation {
  id: string;
  title: string;
  updatedAt: number;
  exchanges: Exchange[];
}

export type ConversationSummary = Pick<
  StoredConversation,
  "id" | "title" | "updatedAt"
>;

const DB_NAME = "nl2sql-ui";
const DB_VERSION = 1;
const STORE = "conversations";
const MAX_CONVERSATIONS = 30;
// Rows are stripped, so this cap is dominated by SQL and analysis text.
const MAX_TOTAL_CHARS = 2_000_000;

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    if (typeof indexedDB === "undefined") {
      reject(new Error("IndexedDB is unavailable"));
      return;
    }
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(STORE)) {
        db.createObjectStore(STORE, { keyPath: "id" });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () =>
      reject(request.error ?? new Error("Failed to open IndexedDB"));
  });
}

function requestResult<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () =>
      reject(request.error ?? new Error("IndexedDB request failed"));
  });
}

async function withStore<T>(
  mode: IDBTransactionMode,
  run: (store: IDBObjectStore) => IDBRequest<T>,
): Promise<T> {
  const db = await openDb();
  try {
    const tx = db.transaction(STORE, mode);
    const completed = new Promise<void>((resolve, reject) => {
      tx.oncomplete = () => resolve();
      tx.onerror = () =>
        reject(tx.error ?? new Error("IndexedDB transaction failed"));
      tx.onabort = () =>
        reject(tx.error ?? new Error("IndexedDB transaction aborted"));
    });
    const result = await requestResult(run(tx.objectStore(STORE)));
    await completed;
    return result;
  } finally {
    db.close();
  }
}

export async function listConversations(): Promise<ConversationSummary[]> {
  try {
    const all = await withStore<StoredConversation[]>("readonly", (store) =>
      store.getAll(),
    );
    return all
      .sort((a, b) => b.updatedAt - a.updatedAt)
      .map(({ id, title, updatedAt }) => ({ id, title, updatedAt }));
  } catch {
    return [];
  }
}

// Mirrors the backend's session-history rule: keep SQL/analysis, never rows.
function stripRows(conversation: StoredConversation): StoredConversation {
  let changed = false;
  const exchanges = conversation.exchanges.map((exchange) => {
    if (!exchange.result || exchange.result.rows.length === 0) {
      return exchange;
    }
    changed = true;
    return {
      ...exchange,
      resultsUnavailable: true,
      result: { ...exchange.result, rows: [] },
    };
  });
  return changed ? { ...conversation, exchanges } : conversation;
}

async function pruneConversations(): Promise<void> {
  const all = await withStore<StoredConversation[]>("readonly", (store) =>
    store.getAll(),
  );
  const ordered = all.sort((a, b) => b.updatedAt - a.updatedAt);
  const keep = new Set<string>();
  let chars = 0;
  for (const conversation of ordered) {
    const size = JSON.stringify(conversation).length;
    if (keep.size >= MAX_CONVERSATIONS || chars + size > MAX_TOTAL_CHARS) {
      break;
    }
    keep.add(conversation.id);
    chars += size;
  }
  const remove = ordered.filter((item) => !keep.has(item.id)).map((item) => item.id);
  if (remove.length === 0) {
    return;
  }
  await withStore<number>("readwrite", (store) => {
    for (const id of remove) {
      store.delete(id);
    }
    return store.count();
  });
}

export async function loadConversation(
  id: string,
): Promise<StoredConversation | null> {
  try {
    const stored = await withStore<StoredConversation | undefined>(
      "readonly",
      (store) => store.get(id),
    );
    if (!stored) {
      return null;
    }
    const clean = stripRows(stored);
    if (clean !== stored) {
      await withStore<IDBValidKey>("readwrite", (store) => store.put(clean));
    }
    return clean;
  } catch {
    return null;
  }
}

export async function saveConversation(
  conversation: StoredConversation,
): Promise<void> {
  try {
    await withStore<IDBValidKey>("readwrite", (store) =>
      store.put(stripRows(conversation)),
    );
    await pruneConversations();
  } catch {
    // Persistence is best effort; the live conversation still works.
  }
}

export async function deleteConversation(id: string): Promise<void> {
  try {
    await withStore<undefined>("readwrite", (store) => store.delete(id));
  } catch {
    // The conversation remains until storage is available again.
  }
}
