import { bytes, canAdmin, canWrite, shortDate, splitFrontmatter } from "./lib";

describe("lib", () => {
  it("splits frontmatter from the body", () => {
    const { meta, body } = splitFrontmatter("---\nname: x\ndescription: Hello there\n---\n\n# Title\n");
    expect(meta).toEqual({ name: "x", description: "Hello there" });
    expect(body).toBe("\n# Title\n");
  });

  it("leaves text without frontmatter alone", () => {
    expect(splitFrontmatter("# Just text").body).toBe("# Just text");
    expect(splitFrontmatter("---\nunclosed").body).toBe("---\nunclosed");
  });

  it("maps roles to abilities", () => {
    expect(canWrite({ role: "reader" })).toBe(false);
    expect(canWrite({ role: "publisher" })).toBe(true);
    expect(canWrite({ role: "admin" })).toBe(true);
    expect(canWrite(null)).toBe(false);
    expect(canAdmin({ role: "publisher" })).toBe(false);
    expect(canAdmin({ role: "admin" })).toBe(true);
  });

  it("formats sizes and dates defensively", () => {
    expect(bytes(10)).toBe("10 B");
    expect(bytes(2048)).toBe("2.0 KiB");
    expect(bytes(3 * 1024 * 1024)).toBe("3.0 MiB");
    expect(shortDate(null)).toBe("-");
    expect(shortDate("not a date")).toBe("not a date");
  });
});
