import { fireEvent, render, screen } from "@testing-library/react";
import { TaskForm } from "../components/TaskForm";
import { I18nProvider } from "../i18n";

describe("TaskForm", () => {
  beforeEach(() => localStorage.setItem("nocix-language", "en-US"));
  it("requires an existing account and visibly locks checkout to PayPal", () => {
    render(<I18nProvider initialLanguage="en-US"><TaskForm onSubmit={vi.fn()} onCancel={vi.fn()} /></I18nProvider>);

    expect(screen.getByText(/payment method/i)).toBeInTheDocument();
    expect(screen.getByText("PayPal")).toBeInTheDocument();
    expect(screen.getByLabelText(/existing nocix email/i)).toBeRequired();
    expect(screen.getByLabelText(/nocix password/i)).toBeRequired();

    expect(document.querySelectorAll("input[name], select[name]"))
      .toHaveLength(0);
  });

  it("translates OS option labels without changing backend enum values", () => {
    const view = render(<I18nProvider initialLanguage="zh-CN"><TaskForm onSubmit={vi.fn()} onCancel={vi.fn()} /></I18nProvider>);
    const operatingSystem = screen.getByLabelText("操作系统");

    expect(screen.getByRole("option", { name: "Debian" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Ubuntu" })).toBeInTheDocument();
    fireEvent.change(operatingSystem, { target: { value: "ubuntu" } });
    expect(operatingSystem).toHaveValue("ubuntu");

    view.unmount();
    render(<I18nProvider initialLanguage="en-US"><TaskForm onSubmit={vi.fn()} onCancel={vi.fn()} /></I18nProvider>);
    expect(screen.getByRole("option", { name: "Debian" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Ubuntu" })).toBeInTheDocument();
  });
});
