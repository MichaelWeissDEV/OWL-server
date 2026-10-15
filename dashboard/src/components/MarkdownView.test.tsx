import { MantineProvider } from "@mantine/core";
import { render, screen } from "@testing-library/react";
import { MarkdownView } from "./MarkdownView";

const show = (source: string) => render(<MantineProvider><MarkdownView source={source} /></MantineProvider>);

describe("MarkdownView (untrusted content)", () => {
  it("renders normal markdown, tables included", () => {
    show("# Title\n\nSome **bold** text.\n\n| a | b |\n|---|---|\n| 1 | 2 |\n");
    expect(screen.getByRole("heading", { name: "Title" })).toBeInTheDocument();
    expect(screen.getByText("bold").tagName).toBe("STRONG");
    expect(screen.getByRole("table")).toBeInTheDocument();
  });

  it("never renders raw HTML or scripts", () => {
    const { container } = show('Hi <script>window.__pwned = 1</script><img src=x onerror="window.__pwned=1"><iframe src="https://evil.example"></iframe>\n\n<div onclick="alert(1)">click</div>');
    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("iframe")).toBeNull();
    expect(container.querySelector("[onclick]")).toBeNull();
    expect(container.querySelector("img")).toBeNull();
    expect((window as unknown as { __pwned?: number }).__pwned).toBeUndefined();
  });

  it("neutralises dangerous link targets", () => {
    const { container } = show("[bad](javascript:alert(1)) [data](data:text/html,<b>x</b>) [good](https://example.com) [mail](mailto:a@b.c)");
    const hrefs = Array.from(container.querySelectorAll("a")).map((a) => a.getAttribute("href"));
    expect(hrefs).toEqual(["https://example.com", "mailto:a@b.c"]);
    expect(screen.getByText("bad")).toBeInTheDocument(); // the text stays, the link goes
  });

  it("opens external links without access to this window", () => {
    show("[site](https://example.com)");
    const link = screen.getByRole("link", { name: "site" });
    expect(link).toHaveAttribute("target", "_blank");
    expect(link.getAttribute("rel")).toContain("noopener");
    expect(link.getAttribute("rel")).toContain("noreferrer");
  });

  it("does not load images (no tracking pixels)", () => {
    const { container } = show("![secret tracker](https://tracker.example/pixel.png)");
    expect(container.querySelector("img")).toBeNull();
    expect(screen.getByText(/image: secret tracker/)).toBeInTheDocument();
  });

  it("hides the frontmatter block", () => {
    show("---\nname: x\ndescription: d\n---\n\n# Body\n");
    expect(screen.queryByText(/description: d/)).toBeNull();
    expect(screen.getByRole("heading", { name: "Body" })).toBeInTheDocument();
  });
});
