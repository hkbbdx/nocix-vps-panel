import { render, screen } from "@testing-library/react";
import { TaskForm } from "../components/TaskForm";

describe("TaskForm", () => {
  it("requires an existing account and visibly locks checkout to PayPal", () => {
    render(<TaskForm onSubmit={vi.fn()} onCancel={vi.fn()} />);

    expect(screen.getByText(/payment method/i)).toBeInTheDocument();
    expect(screen.getByText("PayPal")).toBeInTheDocument();
    expect(screen.getByLabelText(/existing nocix email/i)).toBeRequired();
    expect(screen.getByLabelText(/nocix password/i)).toBeRequired();

    expect(document.querySelectorAll("input[name], select[name]"))
      .toHaveLength(0);
  });
});
