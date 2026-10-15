import { createTheme, type MantineColorsTuple } from "@mantine/core";

// Warm brown/teal palette taken from the OWL logo.
const owl: MantineColorsTuple = [
  "#fdf4ec", "#f4e4d3", "#e8c9a8", "#dcac7b", "#d2935a", "#cb8446", "#c87d3c", "#b06a2e", "#9d5d27", "#8a4e1d",
];

export const theme = createTheme({
  primaryColor: "owl",
  colors: { owl },
  defaultRadius: "md",
  fontFamily: "system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif",
  headings: { fontWeight: "650" },
});
