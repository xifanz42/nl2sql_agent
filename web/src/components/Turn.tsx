import { useState } from "react";
import type { ReactNode } from "react";

import type { ChatResult } from "../api";
import type { Messages } from "../i18n";
import ResultTable from "./ResultTable";


interface TurnProps {
  question: string;
  result?: ChatResult;
  error?: string;
  t: Messages;
}

export default function Turn({ question, result, error, t }: TurnProps) {
  return (
    <article className="turn">
      <p className="question">{question}</p>
      {error ? (
        <div className="answer card">
          <Banner label={t.requestFailed} message={error} />
        </div>
      ) : result ? (
        <Answer result={result} t={t} />
      ) : (
        <div className="answer card is-pending" role="status">
          <span className="pulse" aria-hidden="true" />
          <span>{t.thinking}</span>
        </div>
      )}
    </article>
  );
}

function Answer({ result, t }: { result: ChatResult; t: Messages }) {
  let body: ReactNode = null;
  switch (result.kind) {
    case "sql":
      body = (
        <>
          <div className="analysis">
            {result.analysis || t.queryDone}
          </div>
          {result.rows.length > 0 ? (
            <DataCard rows={result.rows} t={t} />
          ) : (
            <p className="note">{t.noRows}</p>
          )}
          {result.truncated ? (
            <p className="note">{t.truncatedNote(result.rows.length)}</p>
          ) : null}
        </>
      );
      break;
    case "too_many_rows":
      body = (
        <>
          <div className="analysis">{result.message}</div>
          <p className="note">{t.tooManyNote(result.rows.length)}</p>
          {result.rows.length > 0 ? (
            <DataCard rows={result.rows} t={t} />
          ) : null}
        </>
      );
      break;
    case "execution_error":
      body = (
        <>
          <Banner label={t.executionFailed} message={result.message} />
          {result.sql ? (
            <div className="error-sql">
              <SqlBlock sql={result.sql} t={t} />
            </div>
          ) : null}
        </>
      );
      break;
    case "clarification":
    case "refuse":
    case "exploration":
      body = <div className="analysis">{result.message}</div>;
      break;
    case "invalid":
      body = <Banner label={t.invalid} message={result.message} />;
      break;
    case "store_error":
      body = <Banner label={t.storeError} message={result.message} />;
      break;
  }

  return <div className="answer card">{body}</div>;
}

function Banner({ label, message }: { label: string; message: string }) {
  return (
    <div className="banner" data-tone="error">
      <span className="banner-dot" aria-hidden="true" />
      <div className="banner-copy">
        <span className="banner-label">{label}</span>
        {message ? <p className="banner-message">{message}</p> : null}
      </div>
    </div>
  );
}

function DataCard({
  rows,
  t,
}: {
  rows: ChatResult["rows"];
  t: Messages;
}) {
  return (
    <details className="data-card">
      <summary>
        <span className="data-card-title">{t.dataCard}</span>
        <span className="data-card-meta">{t.rowUnit(rows.length)}</span>
        <span className="chevron" aria-hidden="true">
          ⌄
        </span>
      </summary>
      <div className="data-card-body">
        <ResultTable rows={rows} />
      </div>
    </details>
  );
}

function SqlBlock({ sql, t }: { sql: string; t: Messages }) {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(sql);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard can be blocked; the SQL stays selectable.
    }
  };

  return (
    <div className="sql-block">
      <div className="sql-head">
        <span className="sql-tag">SQL</span>
        <button type="button" className="link-button" onClick={copy}>
          {copied ? t.copied : t.copy}
        </button>
      </div>
      <pre>
        <code>{sql}</code>
      </pre>
    </div>
  );
}
