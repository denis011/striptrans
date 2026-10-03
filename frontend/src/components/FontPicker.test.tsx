import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import FontPicker from "./FontPicker";

const options = [
  { value: "", label: "font serijala" },
  { value: "comic-neue-bold", label: "Comic Neue Bold", key: "comic-neue-bold", url: "/api/fonts/comic-neue-bold/file" },
  { value: "bangers", label: "Bangers", key: "bangers", url: "/api/fonts/bangers/file" },
];

describe("FontPicker", () => {
  it("prikazuje fontove sa probom srpskih slova i bira klikom", async () => {
    const onChange = vi.fn();
    render(<FontPicker ariaLabel="Font bloka" value="" options={options} onChange={onChange} />);

    await userEvent.click(screen.getByRole("button", { name: "Font bloka" }));
    expect(screen.getAllByRole("option")).toHaveLength(3);
    expect(screen.getAllByText("ČĆŽŠĐ Aa")).toHaveLength(2); // proba samo uz prave fontove
    await userEvent.click(screen.getByRole("option", { name: /Bangers/ }));

    expect(onChange).toHaveBeenCalledWith("bangers");
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  });

  it("radi i sa tastature", async () => {
    const onChange = vi.fn();
    render(<FontPicker ariaLabel="Font za govor" value="comic-neue-bold" options={options} onChange={onChange} />);

    screen.getByRole("button", { name: "Font za govor" }).focus();
    await userEvent.keyboard("{ArrowDown}{ArrowDown}{Enter}");

    expect(onChange).toHaveBeenCalledWith("bangers");
  });
});
