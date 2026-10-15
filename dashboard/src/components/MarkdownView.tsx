import ReactMarkdown from "react-markdown";
import rehypeSanitize from "rehype-sanitize";
import remarkGfm from "remark-gfm";
import { Anchor, Box } from "@mantine/core";
import { splitFrontmatter } from "../lib";

/**
 * Renders untrusted markdown safely: raw HTML is skipped (never executed), the output is sanitised
 * again, images are not loaded (no tracking pixels, no mixed content) and links may only be
 * http(s), mailto or in-page and open without access to this window.
 */
const SAFE_URL = /^(https?:|mailto:|#)/i;

export function MarkdownView({ source, stripFrontmatter = true }: { source: string; stripFrontmatter?: boolean }) {
  const text = stripFrontmatter ? splitFrontmatter(source).body : source;
  return (
    <Box className="markdown" data-testid="markdown">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeSanitize]}
        skipHtml
        urlTransform={(url) => (SAFE_URL.test(url) ? url : "")}
        components={{
          img: ({ alt }) => <em>[image: {alt ?? "not loaded"}]</em>,
          a: ({ href, children }) =>
            href ? (
              <Anchor href={href} target="_blank" rel="noopener noreferrer nofollow">
                {children}
              </Anchor>
            ) : (
              <span>{children}</span>
            ),
        }}
      >
        {text}
      </ReactMarkdown>
    </Box>
  );
}
