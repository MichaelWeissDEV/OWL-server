import { MantineProvider } from "@mantine/core";
import { render, screen } from "@testing-library/react";
import { DiffView } from "./DiffView";

const show = (a: string, b: string) => render(<MantineProvider><DiffView before={a} after={b} /></MantineProvider>);

describe("DiffView", () => {
  it("marks added and removed lines with text prefixes, not only colour", () => {
    const { container } = show("one\ntwo\nthree\n", "one\nTWO\nthree\n");
    const kinds = Array.from(container.querySelectorAll("[data-kind]")).map((d) => `${d.getAttribute("data-kind")}:${d.textContent}`);
    expect(kinds).toEqual(["same:  one", "removed:- two", "added:+ TWO", "same:  three"]);
  });

  it("says so when nothing differs", () => {
    show("same\n", "same\n");
    expect(screen.getByText("No differences.")).toBeInTheDocument();
  });
});
