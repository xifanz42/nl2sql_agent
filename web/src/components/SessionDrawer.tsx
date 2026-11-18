import { useEffect } from "react";

import type { ConversationSummary } from "../conversations";
import type { Lang, Messages } from "../i18n";
import { localeOf } from "../i18n";

interface SessionDrawerProps {
  open: boolean;
  conversations: ConversationSummary[];
  currentId: string;
  lang: Lang;
  t: Messages;
  disabled?: boolean;
  onClose: () => void;
  onSelect: (id: string) => void;
  onNew: () => void;
}

export default function SessionDrawer({
  open,
  conversations,
  currentId,
  lang,
  t,
  disabled = false,
  onClose,
  onSelect,
  onNew,
}: SessionDrawerProps) {
  useEffect(() => {
    if (!open) {
      return;
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  if (!open) {
    return null;
  }

  const formatter = new Intl.DateTimeFormat(localeOf(lang), {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });

  return (
    <div className="drawer-backdrop" onClick={onClose}>
      <aside
        className="drawer"
        aria-label={t.sessions}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="drawer-head">
          <h2>{t.sessions}</h2>
          <button
            type="button"
            className="icon-button"
            onClick={onClose}
            aria-label={t.close}
          >
            ×
          </button>
        </div>

        <button
          type="button"
          className="button primary drawer-new"
          onClick={onNew}
          disabled={disabled}
        >
          + {t.newConversation}
        </button>

        {conversations.length === 0 ? (
          <p className="drawer-empty">{t.noSessions}</p>
        ) : (
          <ul className="drawer-list">
            {conversations.map((conversation) => (
              <li key={conversation.id}>
                <button
                  type="button"
                  className={`drawer-item${
                    conversation.id === currentId ? " is-active" : ""
                  }`}
                  onClick={() => onSelect(conversation.id)}
                  disabled={disabled}
                >
                  <span className="drawer-item-title">
                    {conversation.title || t.untitled}
                  </span>
                  <span className="drawer-item-time">
                    {formatter.format(conversation.updatedAt)}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </aside>
    </div>
  );
}
