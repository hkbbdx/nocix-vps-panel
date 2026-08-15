import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useLoginMutations } from "../hooks/use-tasks";
import { I18nProvider } from "../i18n";
import { setApiKey } from "../lib/api";

function Probe() {
  const mutations = useLoginMutations();
  return <button onClick={() => void mutations.submitEmailCode.mutateAsync({ id: "task-1", code: "1234" })}>submit</button>;
}

describe("login mutation invalidation", () => {
  it("invalidates orders after accepted code submission", async () => {
    setApiKey("test-key");
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({
      task_id: "task-1", status: "running", waiting: false, attempts: 1, remaining_seconds: 0,
      last_error: null, result: "accepted", message: "verification accepted",
    }), { status: 200 }));
    const client = new QueryClient();
    const invalidate = vi.spyOn(client, "invalidateQueries");
    render(<QueryClientProvider client={client}><I18nProvider><Probe /></I18nProvider></QueryClientProvider>);

    await userEvent.setup().click(screen.getByRole("button", { name: "submit" }));

    await waitFor(() => expect(invalidate).toHaveBeenCalledWith(expect.objectContaining({ queryKey: ["orders"] })));
  });
});
