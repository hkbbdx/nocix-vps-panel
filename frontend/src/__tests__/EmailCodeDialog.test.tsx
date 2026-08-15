import userEvent from "@testing-library/user-event";
import { render, screen, waitFor, within } from "@testing-library/react";
import { EmailCodeDialog } from "../components/EmailCodeDialog";
import { I18nProvider, useTranslation } from "../i18n";

describe("EmailCodeDialog", () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
  });

  it("defaults to Chinese and switches its labels to English", async () => {
    const user = userEvent.setup();
    function LanguageProbe() {
      const { setLanguage } = useTranslation();
      return (
        <>
          <button onClick={() => setLanguage("en-US")}>switch language</button>
          <EmailCodeDialog onSubmit={vi.fn(async () => undefined)} onCancel={vi.fn()} />
        </>
      );
    }

    render(<I18nProvider initialLanguage="zh-CN"><LanguageProbe /></I18nProvider>);
    const dialog = screen.getByRole("dialog", { name: /输入邮箱验证码/i });
    expect(dialog).toBeInTheDocument();
    expect(within(dialog).getByLabelText(/^邮箱验证码$/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "switch language" }));
    expect(screen.getByRole("dialog", { name: /enter email verification code/i })).toBeInTheDocument();
    expect(within(screen.getByRole("dialog")).getByLabelText(/^email verification code$/i)).toBeInTheDocument();
  });

  it("validates digits, clears submitted code, and never stores it", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn(async (code: string) => {
      if (code === "1234") throw new Error("invalid verification code");
    });
    render(<I18nProvider initialLanguage="en-US"><EmailCodeDialog onSubmit={onSubmit} onCancel={vi.fn()} /></I18nProvider>);
    const input = within(screen.getByRole("dialog")).getByLabelText(/^email verification code$/i);

    await user.type(input, "12ab");
    await user.click(screen.getByRole("button", { name: /submit code/i }));
    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent(/4-12 ascii digits/i);

    await user.clear(input);
    await user.type(input, "1234");
    await user.click(screen.getByRole("button", { name: /submit code/i }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/invalid verification code/i));
    expect(input).toHaveValue("");
    expect(localStorage.getItem("1234")).toBeNull();
    expect(sessionStorage.getItem("1234")).toBeNull();
    expect(document.body.textContent).not.toContain("1234");
  });

  it("closes on Escape and restores focus after unmount", async () => {
    const user = userEvent.setup();
    const onCancel = vi.fn();
    const opener = document.createElement("button");
    opener.textContent = "Open code dialog";
    document.body.appendChild(opener);
    opener.focus();
    const view = render(<I18nProvider><EmailCodeDialog onSubmit={vi.fn(async () => undefined)} onCancel={onCancel} /></I18nProvider>);

    await user.keyboard("{Escape}");
    expect(onCancel).toHaveBeenCalledTimes(1);
    view.unmount();
    expect(document.activeElement).toBe(opener);
    opener.remove();
  });
});
