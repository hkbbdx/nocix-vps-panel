import userEvent from "@testing-library/user-event";
import { fireEvent, render, screen } from "@testing-library/react";
import { TaskForm } from "../components/TaskForm";

describe("TaskForm review behavior", () => {
  it("rejects non-positive numeric values before calling onSubmit", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(<TaskForm onSubmit={onSubmit} onCancel={vi.fn()} />);

    await user.type(screen.getByLabelText(/product id/i), "418");
    await user.type(screen.getByLabelText(/existing nocix email/i), "buyer@example.com");
    await user.type(screen.getByLabelText(/nocix password/i), "secret");
    fireEvent.change(screen.getByLabelText(/target price/i), { target: { value: "0" } });
    fireEvent.change(screen.getByLabelText(/check interval/i), { target: { value: "1" } });
    await user.click(screen.getByRole("button", { name: /create task/i }));

    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent(/target price/i);
  });

  it("allows an existing task to keep its configured password and derives cleared URLs", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(<TaskForm task={{
      id: "task-1", goods_id: "418", stock_url: "https://nocix.net/out-of-stock/?id=418", cart_url: "https://nocix.net/cart/?id=418",
      target_price: 10, wait_interval: 5, operating_system: "debian", email: "buyer@example.com", new_customer: false,
      payment_method: "paypal", auto_submit: true, password_configured: true, status: "stopped", last_stock_status: null,
      last_checked_at: null, last_error: null,
    }} onSubmit={onSubmit} onCancel={vi.fn()} />);

    expect(screen.getByLabelText(/nocix password/i)).not.toBeRequired();
    await user.clear(screen.getByLabelText(/stock url/i));
    await user.clear(screen.getByLabelText(/cart url/i));
    await user.click(screen.getByRole("button", { name: /save changes/i }));

    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({
      stock_url: "https://nocix.net/out-of-stock/?id=418",
      cart_url: "https://nocix.net/cart/?id=418",
    }));
    expect(onSubmit.mock.calls[0][0]).not.toHaveProperty("password");
  });

  it.each([
    ["email", "not-an-email", /valid email/i],
    ["stock url", "https://example.com/stock", /nocix host/i],
    ["cart url", "not a url", /valid http/i],
  ])("rejects invalid %s before mutation", async (field, value, message) => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(<TaskForm onSubmit={onSubmit} onCancel={vi.fn()} />);
    await user.type(screen.getByLabelText(/product id/i), "418");
    await user.type(screen.getByLabelText(/target price/i), "10");
    await user.clear(screen.getByLabelText(/check interval/i));
    await user.clear(screen.getByLabelText(/check interval/i));
    await user.type(screen.getByLabelText(/check interval/i), "2");
    await user.type(screen.getByLabelText(/existing nocix email/i), "buyer@example.com");
    await user.type(screen.getByLabelText(/nocix password/i), "secret");
    await user.clear(screen.getByLabelText(new RegExp(field, "i")));
    await user.type(screen.getByLabelText(new RegExp(field, "i")), value);
    await user.click(screen.getByRole("button", { name: /create task/i }));
    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent(message);
  });

  it("rejects fractional intervals before mutation", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(<TaskForm onSubmit={onSubmit} onCancel={vi.fn()} />);
    await user.type(screen.getByLabelText(/product id/i), "418");
    await user.type(screen.getByLabelText(/target price/i), "10");
    await user.clear(screen.getByLabelText(/check interval/i));
    await user.type(screen.getByLabelText(/check interval/i), "2.5");
    await user.type(screen.getByLabelText(/existing nocix email/i), "buyer@example.com");
    await user.type(screen.getByLabelText(/nocix password/i), "secret");
    await user.click(screen.getByRole("button", { name: /create task/i }));
    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent(/whole number/i);
  });
});
