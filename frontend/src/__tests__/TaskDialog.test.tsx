import userEvent from "@testing-library/user-event";
import { render, screen } from "@testing-library/react";
import { TaskDialog } from "../components/TaskDialog";
import { I18nProvider } from "../i18n";

describe("TaskDialog", () => {
  beforeEach(() => localStorage.setItem("nocix-language", "en-US"));
  it("exposes dialog semantics, focuses its form, and closes on Escape", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(<I18nProvider initialLanguage="en-US"><TaskDialog onSubmit={vi.fn()} onClose={onClose} /></I18nProvider>);

    const dialog = screen.getByRole("dialog", { name: /watch a nocix product/i });
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(dialog).toHaveAttribute("aria-describedby", "task-dialog-description");
    expect(screen.getByLabelText(/product id/i)).toHaveFocus();

    await user.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("wraps Tab focus within the dialog and restores focus to the opener", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    const opener = document.createElement("button");
    opener.textContent = "Open";
    opener.dataset.testid = "opener";
    document.body.appendChild(opener);
    opener.focus();
    const { unmount } = render(<I18nProvider initialLanguage="en-US"><TaskDialog onSubmit={vi.fn()} onClose={onClose} /></I18nProvider>);
    const dialog = screen.getByRole("dialog");
    const buttons = screen.getAllByRole("button");
    const close = screen.getByRole("button", { name: /close task form/i });
    close.focus();

    await user.keyboard("{Tab}");
    expect(document.activeElement).toBe(screen.getByLabelText(/product id/i));
    await user.keyboard("{Shift>}{Tab}{/Shift}");
    expect(document.activeElement).toBe(close);
    expect(dialog).toBeInTheDocument();
    unmount();
    expect(document.activeElement).toBe(opener);
    expect(buttons.length).toBeGreaterThan(1);
    opener.remove();
  });
});
