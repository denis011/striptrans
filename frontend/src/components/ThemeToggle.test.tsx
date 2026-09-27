import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import { THEME_KEY } from "../theme";
import ThemeToggle from "./ThemeToggle";

afterEach(() => {
  localStorage.clear();
  document.documentElement.removeAttribute("data-theme");
});

describe("prekidač teme", () => {
  it("menja temu kao sistem → svetla → tamna i pamti izbor", async () => {
    render(<ThemeToggle />);

    await userEvent.click(screen.getByRole("button", { name: "Tema: kao sistem" }));
    expect(document.documentElement.dataset.theme).toBe("light");
    await userEvent.click(screen.getByRole("button", { name: "Tema: svetla" }));
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(JSON.parse(localStorage.getItem(THEME_KEY) ?? "null")).toBe("dark");
    await userEvent.click(screen.getByRole("button", { name: "Tema: tamna" }));
    expect(document.documentElement.hasAttribute("data-theme")).toBe(false);
  });

  it("počinje od zapamćene teme", () => {
    localStorage.setItem(THEME_KEY, JSON.stringify("dark"));

    render(<ThemeToggle />);

    expect(screen.getByRole("button", { name: "Tema: tamna" })).toBeInTheDocument();
  });
});
