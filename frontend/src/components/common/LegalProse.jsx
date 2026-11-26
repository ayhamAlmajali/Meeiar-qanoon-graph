import { Fragment } from "react";
import { Icon } from "./UI";

function renderInlineBold(text) {
  const parts = String(text).split(/(\*\*[^*]+\*\*)/g);
  return parts.map((part, index) => {
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
      return <strong key={index} className="font-semibold text-slate-900">{part.slice(2, -2)}</strong>;
    }
    return <Fragment key={index}>{part}</Fragment>;
  });
}

function isHeadingLine(line) {
  return /^(?:#{1,3}\s+|\d+\.\s+.{2,80}:?$|\*\*[^*]{3,70}:?\*\*:?$)/.test(line);
}

function cleanHeading(line) {
  return line
    .replace(/^#{1,3}\s+/, "")
    .replace(/^\*\*|\*\*$/g, "")
    .replace(/:$/, "")
    .trim();
}

export default function LegalProse({ text, className = "" }) {
  const raw = typeof text === "string" ? text.trim() : "";
  if (!raw) return null;

  const lines = raw.split(/\r?\n/);
  const blocks = [];
  let listItems = [];

  const flushList = () => {
    if (listItems.length > 0) {
      blocks.push({ type: "list", items: listItems });
      listItems = [];
    }
  };

  lines.forEach((rawLine) => {
    const line = rawLine.trim();
    if (!line) {
      flushList();
      return;
    }

    if (/^تنبيه تدقيق آلي[:：]/.test(line)) {
      flushList();
      blocks.push({ type: "warning", text: line });
      return;
    }

    if (/^[-•*]\s+/.test(line)) {
      listItems.push(line.replace(/^[-•*]\s+/, ""));
      return;
    }

    flushList();
    if (isHeadingLine(line) && line.length < 110) {
      blocks.push({ type: "heading", text: cleanHeading(line) });
    } else {
      blocks.push({ type: "paragraph", text: line });
    }
  });
  flushList();

  return (
    <div className={`legal-prose ${className}`.trim()} dir="rtl" lang="ar">
      {blocks.map((block, index) => {
        if (block.type === "heading") {
          return <h4 key={index} className="legal-prose-heading">{renderInlineBold(block.text)}</h4>;
        }
        if (block.type === "list") {
          return (
            <ul key={index} className="legal-prose-list">
              {block.items.map((item, itemIdx) => <li key={itemIdx}>{renderInlineBold(item)}</li>)}
            </ul>
          );
        }
        if (block.type === "warning") {
          return (
            <div key={index} className="legal-prose-warning" role="note">
              <Icon name="alert" size={18} />
              <span>{renderInlineBold(block.text)}</span>
            </div>
          );
        }
        return <p key={index}>{renderInlineBold(block.text)}</p>;
      })}
    </div>
  );
}
