import * as React from "react";
import { cn } from "@/lib/utils";

/** Inline: **bold**, *italic*, `code`. Output is React nodes, never raw HTML. */
function inline(text: string, key: string): React.ReactNode[] {
  const out: React.ReactNode[] = [];
  const re = /(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let i = 0;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(text.slice(last, m.index));
    const tok = m[0];
    if (tok.startsWith("**")) out.push(<strong key={`${key}-${i++}`}>{tok.slice(2, -2)}</strong>);
    else if (tok.startsWith("`")) out.push(<code key={`${key}-${i++}`} className="rounded bg-surface-2 px-1 text-[0.9em]">{tok.slice(1, -1)}</code>);
    else out.push(<em key={`${key}-${i++}`}>{tok.slice(1, -1)}</em>);
    last = m.index + tok.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

/** Minimal, safe markdown for twin output: headings, lists, quotes, paragraphs. */
export function Markdown({ text, className }: { text: string; className?: string }) {
  const blocks: React.ReactNode[] = [];
  let list: { ordered: boolean; items: string[] } | null = null;
  const flush = () => {
    if (!list) return;
    const Tag = list.ordered ? "ol" : "ul";
    blocks.push(
      <Tag key={`l${blocks.length}`} className={cn("ml-5 space-y-1", list.ordered ? "list-decimal" : "list-disc")}>
        {list.items.map((it, i) => (
          <li key={i}>{inline(it, `li${blocks.length}-${i}`)}</li>
        ))}
      </Tag>,
    );
    list = null;
  };
  text.split("\n").forEach((raw, n) => {
    const line = raw.trimEnd();
    const bullet = /^\s*[-*]\s+(.*)$/.exec(line);
    const num = /^\s*\d+\.\s+(.*)$/.exec(line);
    if (bullet || num) {
      const ordered = !!num;
      if (!list || list.ordered !== ordered) {
        flush();
        list = { ordered, items: [] };
      }
      list.items.push((bullet ?? num)![1]!);
      return;
    }
    flush();
    if (!line.trim()) return;
    const h = /^(#{1,3})\s+(.*)$/.exec(line);
    if (h) {
      const size = h[1]!.length === 1 ? "text-base" : "text-sm";
      blocks.push(<p key={n} className={cn("mt-2 font-semibold", size)}>{inline(h[2]!, `h${n}`)}</p>);
    } else if (line.startsWith(">")) {
      blocks.push(<blockquote key={n} className="border-l-2 border-accent pl-3 text-muted">{inline(line.slice(1).trim(), `q${n}`)}</blockquote>);
    } else {
      blocks.push(<p key={n}>{inline(line, `p${n}`)}</p>);
    }
  });
  flush();
  return <div className={cn("space-y-2 text-sm leading-relaxed", className)}>{blocks}</div>;
}
