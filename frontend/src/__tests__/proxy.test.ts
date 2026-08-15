import { isValidProxyUrl } from "../lib/proxy";

describe("proxy URL validation", () => {
  it.each([
    "http://proxy.example.com:8080",
    "socks5://user:password@proxy.example.com:1080",
    "http://proxy.example.net:3128",
  ])("accepts %s", (value) => {
    expect(isValidProxyUrl(value)).toBe(true);
  });

  it.each([
    "https://proxy.example.com:8080",
    "http://proxy.example.com",
    "http://proxy.example.com:0",
    "http://proxy.example.com:65536",
    "http://proxy.example.com:8080/path",
    "http://proxy.example.com:8080/",
    "http://proxy.example.com:8080?secret=value",
    "http://proxy.example.com:8080#fragment",
    "http://localhost:8080",
    "http://127.0.0.1:8080",
    "http://10.0.0.1:8080",
    "http://169.254.169.254:8080",
    "http://[::1]:8080",
    "http://2130706433:8080",
    "http://0x7f000001:8080",
    "http://0177.0.0.1:8080",
    "http://proxy..example:8080",
    "http://-proxy.example:8080",
    "http://proxy-.example:8080",
    "http://proxy%2eexample:8080",
    "http://proxy_underscore.example:8080",
    "http://代理.example:8080",
    "http://proxy.example.com:8080/with space",
  ])("rejects unsafe or unsupported URL %s", (value) => {
    expect(isValidProxyUrl(value)).toBe(false);
  });

  it("accepts percent-encoded credential delimiters but not raw delimiters", () => {
    expect(isValidProxyUrl("http://user:pa%40ss@proxy.example.com:8080")).toBe(true);
    expect(isValidProxyUrl("http://user:pa@ss@proxy.example.com:8080")).toBe(false);
  });

  it("rejects malformed credential percent escapes while allowing valid escapes", () => {
    expect(isValidProxyUrl("http://us%ZZer:password@proxy.example.com:8080")).toBe(false);
    expect(isValidProxyUrl("http://user:pass%2@proxy.example.com:8080")).toBe(false);
    expect(isValidProxyUrl("http://user:pa%40ss@proxy.example.com:8080")).toBe(true);
  });
});
