const mocks = vi.hoisted(() => ({ useQuery: vi.fn() }));

vi.mock("@tanstack/react-query", () => ({ useQuery: mocks.useQuery, useMutation: vi.fn(), useQueryClient: vi.fn(() => ({ invalidateQueries: vi.fn() })) }));

import { render } from "@testing-library/react";
import { LOGIN_STATE_POLL_INTERVAL, useLoginState } from "../hooks/use-tasks";
import type { TaskStatus } from "../lib/types";

function Probe({ status }: { status: TaskStatus }) {
  useLoginState("task-1", status);
  return null;
}

describe("login state polling", () => {
  it("polls only while waiting and uses a bounded interval", () => {
    sessionStorage.setItem("nocix-api-key", "test-key");
    mocks.useQuery.mockReturnValue({ data: undefined, error: null });
    const view = render(<Probe status="waiting_for_email_code" />);
    expect(LOGIN_STATE_POLL_INTERVAL).toBe(5_000);
    const waitingOptions = mocks.useQuery.mock.lastCall?.[0];
    expect(waitingOptions).toBeDefined();
    expect(waitingOptions).toEqual(expect.objectContaining({
      queryKey: ["task-login-state", "task-1"],
      enabled: true,
    }));
    expect(typeof waitingOptions.refetchInterval).toBe("function");

    view.rerender(<Probe status="login_second" />);
    const inactiveOptions = mocks.useQuery.mock.lastCall?.[0];
    expect(inactiveOptions).toBeDefined();
    expect(inactiveOptions.enabled).toBe(false);
    expect(inactiveOptions.refetchInterval({ state: { data: undefined, error: null } })).toBe(false);
  });
});
