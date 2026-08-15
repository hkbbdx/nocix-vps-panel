import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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

  it("shows bilingual proxy modes and validates a custom proxy without exposing the URL in the error", async () => {
    const onSubmit = vi.fn();
    render(<I18nProvider initialLanguage="en-US"><TaskForm onSubmit={onSubmit} onCancel={vi.fn()} /></I18nProvider>);

    const mode = screen.getByLabelText("Proxy mode");
    expect(screen.getByRole("option", { name: "Use global proxy" })).toBeInTheDocument();
    fireEvent.change(mode, { target: { value: "custom" } });
    const proxyUrl = screen.getByLabelText("Custom proxy URL");
    expect(proxyUrl).toHaveAttribute("type", "password");
    fireEvent.change(proxyUrl, { target: { value: "http://proxy.example.com:8080?token=secret" } });
    fireEvent.change(screen.getByLabelText("Product ID"), { target: { value: "418" } });
    fireEvent.change(screen.getByLabelText("Target price"), { target: { value: "10" } });
    fireEvent.change(screen.getByLabelText(/existing nocix email/i), { target: { value: "buyer@example.com" } });
    fireEvent.change(screen.getByLabelText(/nocix password/i), { target: { value: "account-secret" } });
    fireEvent.submit(screen.getByRole("button", { name: "Create task" }).closest("form")!);

    expect(await screen.findByRole("alert")).toHaveTextContent("Proxy URL must use http:// or socks5:// with a valid host and port, without a query or fragment.");
    expect(screen.getByRole("alert")).not.toHaveTextContent("secret");
    expect(onSubmit).not.toHaveBeenCalled();
    await waitFor(() => expect(screen.getByLabelText("Proxy mode")).toHaveValue("custom"));
  });
});
