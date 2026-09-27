import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import Menu from "./Menu";

function renderMenu(onAction = vi.fn()) {
  render(
    <>
      <Menu label="Blokovi">
        <button type="button" onClick={onAction}>
          Spoji
        </button>
        <label>
          <input type="checkbox" /> Prikaži blokove
        </label>
      </Menu>
      <p>van menija</p>
    </>,
  );
  return onAction;
}

describe("padajući meni", () => {
  it("radnja zatvara meni, a izbor ga ostavlja otvorenim", async () => {
    const onAction = renderMenu();
    const toggle = screen.getByRole("button", { name: "Blokovi" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");

    await userEvent.click(toggle);
    await userEvent.click(screen.getByLabelText("Prikaži blokove"));
    expect(screen.getByRole("group", { name: "Blokovi" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Spoji" }));

    expect(onAction).toHaveBeenCalledOnce();
    expect(screen.queryByRole("group", { name: "Blokovi" })).not.toBeInTheDocument();
  });

  it("zatvara se klikom van menija i tasterom Esc, koji ne ide dalje", async () => {
    renderMenu();
    const onWindowKey = vi.fn();
    window.addEventListener("keydown", onWindowKey);

    await userEvent.click(screen.getByRole("button", { name: "Blokovi" }));
    await userEvent.click(screen.getByText("van menija"));
    expect(screen.queryByRole("group", { name: "Blokovi" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Blokovi" }));
    await userEvent.keyboard("{Escape}");

    expect(screen.queryByRole("group", { name: "Blokovi" })).not.toBeInTheDocument();
    expect(onWindowKey).not.toHaveBeenCalled();
    window.removeEventListener("keydown", onWindowKey);
  });
});
