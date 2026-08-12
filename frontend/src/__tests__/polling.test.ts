import { ORDERS_POLL_INTERVAL } from "../hooks/use-orders";
import { SETTINGS_POLL_INTERVAL } from "../hooks/use-settings";

describe("bounded query polling", () => {
  it("uses bounded intervals for orders and settings", () => {
    expect(ORDERS_POLL_INTERVAL).toBe(15_000);
    expect(SETTINGS_POLL_INTERVAL).toBe(30_000);
  });
});
