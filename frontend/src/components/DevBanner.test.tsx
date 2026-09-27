import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DevBanner } from "../App";

describe("razvojno okruženje", () => {
  it("crveni okvir kaže da je ovo kopija i gde je pravi rad", () => {
    render(<DevBanner />);
    expect(screen.getByRole("note", { name: "Razvojno okruženje" })).toHaveTextContent("DEV — razvojna kopija, izmene se ne čuvaju");
    expect(screen.getByText(/localhost:5173/)).toBeInTheDocument();
  });
});
