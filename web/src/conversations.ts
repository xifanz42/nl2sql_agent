import type { ChatResult } from "./api";

export interface Exchange {
  id: string;
  question: string;
  result?: ChatResult;
  error?: string;
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

export async function loadConversation(
  id: string,
): Promise<StoredConversation | null> {
  try {
    const stored = await withStore<StoredConversation | undefined>(
      "readonly",
      (store) => store.get(id),
    );
    return stored ?? null;
  } catch {
    return null;
  }
}

export async function saveConversation(
  conversation: StoredConversation,
): Promise<void> {
  try {
    await withStore<IDBValidKey>("readwrite", (store) => store.put(conversation));
  } catch {
    // Persistence is best effort; the live conversation still works.
  }
}
