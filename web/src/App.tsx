import { useEffect, useMemo, useRef, useState } from "react";
import type { ChangeEvent, FormEvent, KeyboardEvent } from "react";

import {
  ApiError,
  currentSessionId,
  getMaxMessageChars,
  newSessionId,
  postChat,
  randomUuid,
  storeSessionId,
  uploadDocument,
} from "./api";
import type {
  ConversationSummary,
  Exchange,
} from "./conversations";
import {
  deleteConversation,
  listConversations,
  loadConversation,
  saveConversation,
} from "./conversations";
import type { Lang } from "./i18n";
import { MESSAGES, detectLang, localeOf, storeLang } from "./i18n";
import SessionDrawer from "./components/SessionDrawer";
import Turn from "./components/Turn";

interface UploadState {
  tone: "idle" | "pending" | "ok" | "error";
  text: string;
}

interface UsageTotals {
  tokens: number;
  calls: number;
  cost: number;
  unpriced: boolean;
}

// Stored ids may predate per-exchange UUIDs and contain duplicates; re-key on
// load so React keys stay unique and in-flight updates match exactly one turn.
function withFreshIds(exchanges: Exchange[]): Exchange[] {
  return exchanges.map((exchange) => ({ ...exchange, id: randomUuid() }));
}

// Two significant digits keep cheap-model costs readable (¥0.00012 instead of
// ¥0.0000). CNY is the only billed currency, so it is labelled rather than
// converted; a lower bound is marked with ≥.
function formatCost(cost: number, unpriced: boolean, lang: Lang): string {
  if (!Number.isFinite(cost)) {
    return "—";
  }
  const unit = lang === "zh" ? "¥" : "CNY ";
  if (unpriced && cost === 0) {
    return lang === "zh" ? "未定价" : "unpriced";
  }
  const prefix = unpriced ? "≥" : "≈";
  if (cost === 0) {
    return `${prefix}${unit}0`;
  }
  if (cost < 0.000001) {
    return `${prefix}<${unit}0.000001`;
  }
  if (cost < 1) {
    return `${prefix}${unit}${String(Number(cost.toPrecision(2)))}`;
  }
  return `${prefix}${unit}${cost.toFixed(2)}`;
}

export default function App() {
  const [lang, setLang] = useState<Lang>(() => detectLang());
  const [sessionId, setSessionId] = useState(() => currentSessionId());
  const [exchanges, setExchanges] = useState<Exchange[]>([]);
  const [input, setInput] = useState("");
  const [pending, setPending] = useState(false);
  const [upload, setUpload] = useState<UploadState>({ tone: "idle", text: "" });
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [sessionsOpen, setSessionsOpen] = useState(false);
  const [showUsage, setShowUsage] = useState(false);
  const [maxChars, setMaxChars] = useState(2000);
  // Timestamp of the last user-visible activity. Loading a conversation keeps
  // its stored value so reading history does not reorder the drawer.
  const lastActivityAt = useRef(Date.now());
  const t = MESSAGES[lang];

  useEffect(() => {
    document.documentElement.lang = localeOf(lang);
  }, [lang]);

  // Mirror the server's message limit; 2000 matches the backend default.
  useEffect(() => {
    let cancelled = false;
    void getMaxMessageChars().then((limit) => {
      if (!cancelled && limit && limit > 0) {
        setMaxChars(limit);
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);

  // Restore the conversation that matches the session id kept in localStorage.
  useEffect(() => {
    let cancelled = false;
    void loadConversation(sessionId).then((stored) => {
      if (!cancelled && stored && stored.exchanges.length > 0) {
        lastActivityAt.current = stored.updatedAt;
        setExchanges(withFreshIds(stored.exchanges));
      }
    });
    return () => {
      cancelled = true;
    };
    // Runs once for the initially restored session.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (exchanges.length === 0) {
      return;
    }
    const conversation = {
      id: sessionId,
      title: exchanges[0].question.slice(0, 60),
      updatedAt: lastActivityAt.current,
      exchanges: exchanges.slice(-50),
    };
    void saveConversation(conversation).then(async () => {
      setConversations(await listConversations());
    });
  }, [exchanges, sessionId]);

  // Scroll the page itself: scrolling an element to its own end leaves the
  // reply hidden behind the fixed composer.
  useEffect(() => {
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let inner = 0;
    const outer = window.requestAnimationFrame(() => {
      inner = window.requestAnimationFrame(() => {
        window.scrollTo({
          top: document.documentElement.scrollHeight,
          behavior: reduce ? "auto" : "smooth",
        });
      });
    });
    return () => {
      window.cancelAnimationFrame(outer);
      window.cancelAnimationFrame(inner);
    };
  }, [exchanges]);

  const usage = useMemo<UsageTotals>(
    () =>
      exchanges.reduce<UsageTotals>(
        (totals, exchange) => {
          const result = exchange.result;
          if (!result) {
            return totals;
          }
          return {
            tokens:
              totals.tokens + result.prompt_tokens + result.completion_tokens,
            calls: totals.calls + result.calls,
            cost:
              totals.cost +
              (Number.isFinite(result.cost_cny) ? result.cost_cny : 0),
            unpriced: totals.unpriced || result.unpriced_models.length > 0,
          };
        },
        { tokens: 0, calls: 0, cost: 0, unpriced: false },
      ),
    [exchanges],
  );

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const question = input.trim();
    if (!question || pending) {
      return;
    }
    const id = randomUuid();
    lastActivityAt.current = Date.now();
    setExchanges((prev) => [...prev, { id, question }]);
    setInput("");
    setPending(true);
    try {
      const response = await postChat(question);
      lastActivityAt.current = Date.now();
      setSessionId(response.session_id);
      setExchanges((prev) =>
        prev.map((item) =>
          item.id === id ? { ...item, result: response.result } : item,
        ),
      );
    } catch (error) {
      const message =
        error instanceof ApiError
          ? error.message || t.httpError(error.status)
          : t.networkError;
      lastActivityAt.current = Date.now();
      setExchanges((prev) =>
        prev.map((item) => (item.id === id ? { ...item, error: message } : item)),
      );
    } finally {
      setPending(false);
    }
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (
      event.key === "Enter" &&
      !event.shiftKey &&
      !event.nativeEvent.isComposing
    ) {
      event.preventDefault();
      event.currentTarget.form?.requestSubmit();
    }
  };

  const handleUpload = async (event: ChangeEvent<HTMLInputElement>) => {
    const picker = event.currentTarget;
    const file = picker.files?.[0];
    picker.value = "";
    if (!file) {
      return;
    }
    setUpload({ tone: "pending", text: t.uploadPending(file.name) });
    try {
      const filename = await uploadDocument(file);
      setUpload({ tone: "ok", text: t.uploaded(filename ?? file.name) });
    } catch (error) {
      setUpload({
        tone: "error",
        text:
          error instanceof ApiError
            ? error.message || t.httpError(error.status)
            : t.uploadFailed,
      });
    }
  };

  const handleNewConversation = () => {
    if (pending) {
      return;
    }
    const id = newSessionId();
    setSessionId(id);
    setExchanges([]);
    setInput("");
    setUpload({ tone: "idle", text: "" });
    setSessionsOpen(false);
  };

  const handleOpenSessions = async () => {
    setConversations(await listConversations());
    setSessionsOpen(true);
  };

  const handleDeleteConversation = async (id: string) => {
    if (pending) {
      return;
    }
    const target = conversations.find((conversation) => conversation.id === id);
    if (!window.confirm(t.deleteConfirm(target?.title || t.untitled))) {
      return;
    }
    await deleteConversation(id);
    if (id === sessionId) {
      setSessionId(newSessionId());
      setExchanges([]);
      setInput("");
      setUpload({ tone: "idle", text: "" });
      setSessionsOpen(false);
      lastActivityAt.current = Date.now();
    }
    setConversations(await listConversations());
  };

  const handleSelectConversation = async (id: string) => {
    setSessionsOpen(false);
    if (pending || id === sessionId) {
      return;
    }
    const stored = await loadConversation(id);
    storeSessionId(id);
    setSessionId(id);
    lastActivityAt.current = stored?.updatedAt ?? Date.now();
    setExchanges(withFreshIds(stored?.exchanges ?? []));
    setInput("");
  };

  const handleLangChange = (next: Lang) => {
    setLang(next);
    storeLang(next);
  };

  return (
    <>
      <header className="topbar">
        <div className="brand">
          <span className="brand-name">NL2SQL</span>
          <span className="brand-sub">{t.brandSub}</span>
        </div>
        <div className="topbar-actions">
          <button
            type="button"
            className="button ghost"
            onClick={handleOpenSessions}
          >
            {t.sessions}
          </button>
          <label className="button ghost">
            {t.upload}
            <input
              type="file"
              accept=".pdf,.txt,.csv,.md,.markdown"
              onChange={handleUpload}
              disabled={upload.tone === "pending"}
              hidden
            />
          </label>
          <button
            type="button"
            className="button ghost"
            onClick={handleNewConversation}
            disabled={pending}
          >
            {t.newConversation}
          </button>
          <div className="lang-toggle" role="group" aria-label={t.language}>
            <button
              type="button"
              className={lang === "zh" ? "is-active" : ""}
              onClick={() => handleLangChange("zh")}
            >
              中文
            </button>
            <button
              type="button"
              className={lang === "en" ? "is-active" : ""}
              onClick={() => handleLangChange("en")}
            >
              EN
            </button>
          </div>
        </div>
      </header>

      {upload.text ? (
        <div className="upload-status" data-tone={upload.tone} role="status">
          <span className="status-dot" aria-hidden="true" />
          {upload.text}
        </div>
      ) : null}

      <main className="transcript">
        {exchanges.length === 0 ? (
          <section className="empty">
            <h1>{t.emptyTitle}</h1>
            <p>{t.emptyBody}</p>
          </section>
        ) : (
          exchanges.map((exchange) => (
            <Turn
              key={exchange.id}
              question={exchange.question}
              result={exchange.result}
              error={exchange.error}
              resultsUnavailable={exchange.resultsUnavailable}
              t={t}
            />
          ))
        )}
        {showUsage && usage.calls > 0 ? (
          <p className="idle-hint" role="status" id="usage-hint">
            <span className="status-dot" aria-hidden="true" />
            {t.idleHint(
              usage.tokens.toLocaleString(localeOf(lang)),
              usage.calls,
              formatCost(usage.cost, usage.unpriced, lang),
            )}
          </p>
        ) : null}
      </main>

      <div className="composer-shell">
        <form className="composer" onSubmit={handleSubmit}>
          <textarea
            value={input}
            onChange={(event) => setInput(event.currentTarget.value)}
            onKeyDown={handleKeyDown}
            rows={2}
            maxLength={maxChars}
            placeholder={t.placeholder}
            aria-label={t.placeholder}
          />
          <button
            type="submit"
            className="button primary"
            disabled={pending || !input.trim()}
          >
            {pending ? t.sending : t.send}
          </button>
        </form>
        <div className="composer-hint">
          <span className="hint-text">{t.composerHint}</span>
          {usage.calls > 0 ? (
            <button
              type="button"
              className="usage-toggle"
              onClick={() => setShowUsage((visible) => !visible)}
              aria-controls="usage-hint"
              aria-expanded={showUsage}
            >
              {showUsage ? t.hideUsage : t.usage}
            </button>
          ) : null}
        </div>
      </div>

      <SessionDrawer
        open={sessionsOpen}
        conversations={conversations}
        currentId={sessionId}
        lang={lang}
        t={t}
        disabled={pending}
        onClose={() => setSessionsOpen(false)}
        onSelect={(id) => void handleSelectConversation(id)}
        onNew={handleNewConversation}
        onDelete={(id) => void handleDeleteConversation(id)}
      />
    </>
  );
}
