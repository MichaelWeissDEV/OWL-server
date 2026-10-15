import { diffLines } from "diff";
import { Code, Text } from "@mantine/core";

/** A unified-style line diff. Prefixes (+/-/space) carry the meaning too, not only colour. */
export function DiffView({ before, after, labels = ["before", "after"] }: { before: string; after: string; labels?: [string, string] }) {
  const parts = diffLines(before, after);
  const changed = parts.some((p) => p.added || p.removed);
  if (!changed) return <Text c="dimmed">No differences.</Text>;
  return (
    <Code block data-testid="diff" aria-label={`Differences between ${labels[0]} and ${labels[1]}`} style={{ whiteSpace: "pre-wrap" }}>
      {parts.flatMap((part, i) => {
        const prefix = part.added ? "+ " : part.removed ? "- " : "  ";
        return part.value
          .replace(/\n$/, "")
          .split("\n")
          .map((line, j) => (
            <div
              key={`${i}-${j}`}
              data-kind={part.added ? "added" : part.removed ? "removed" : "same"}
              style={{
                background: part.added ? "var(--mantine-color-teal-light)" : part.removed ? "var(--mantine-color-red-light)" : undefined,
              }}
            >
              {prefix}
              {line}
            </div>
          ));
      })}
    </Code>
  );
}
