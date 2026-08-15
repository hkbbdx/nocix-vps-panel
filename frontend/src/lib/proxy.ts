const PROXY_SCHEMES = new Set(["http:", "socks5:"]);

function hasValidPercentEscapes(value: string): boolean {
  for (let index = 0; index < value.length; index += 1) {
    if (value[index] === "%" && !/^%[0-9A-Fa-f]{2}/.test(value.slice(index))) return false;
  }
  return true;
}

function isPrivateIpv4(hostname: string): boolean {
  if (!/^[0-9.]+$/.test(hostname)) return false;
  if (!/^\d{1,3}(?:\.\d{1,3}){3}$/.test(hostname)) return true;
  const parts = hostname.split(".").map(Number);
  if (parts.length !== 4 || parts.some((part) => !Number.isInteger(part) || part < 0 || part > 255)) return true;
  const [first, second] = parts;
  return first === 0 || first === 10 || first === 127 || (first === 100 && second >= 64 && second <= 127) || (first === 169 && second === 254) || (first === 172 && second >= 16 && second <= 31) || (first === 192 && second === 0 && parts[2] === 0) || (first === 192 && second === 168) || (first === 198 && (second === 18 || second === 19)) || (first === 198 && second === 51 && parts[2] === 100) || (first === 203 && second === 0 && parts[2] === 113);
}

function isPrivateIpv6(hostname: string): boolean {
  const normalized = hostname.replace(/^\[|\]$/g, "").toLowerCase();
  if (!normalized.includes(":")) return false;
  return normalized === "::" || normalized === "::1" || normalized.startsWith("fc") || normalized.startsWith("fd") || normalized.startsWith("fe8") || normalized.startsWith("fe9") || normalized.startsWith("fea") || normalized.startsWith("feb") || normalized.startsWith("ff");
}

function hasValidDnsLabels(hostname: string): boolean {
  if (hostname.length > 253) return false;
  return hostname.split(".").every((label) => label.length > 0 && label.length <= 63 && /^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/i.test(label));
}

function isAmbiguousNumericHost(hostname: string): boolean {
  return /^(?:\d+|0[xX][0-9a-f]+|0[0-7]+)$/.test(hostname);
}

export function isValidProxyUrl(value: string): boolean {
  if (!value || /\s|[\u0000-\u001f\u007f]/.test(value)) return false;
  if (!value.startsWith("http://") && !value.startsWith("socks5://")) return false;
  try {
    const parsed = new URL(value);
    const hostname = parsed.hostname.toLowerCase().replace(/^\[|\]$/g, "");
    const remainder = value.slice(value.indexOf("//") + 2);
    const authority = remainder.split(/[/?#]/, 1)[0];
    const hasExplicitPath = remainder[authority.length] === "/";
    const hostPart = authority.slice(authority.lastIndexOf("@") + 1).replace(/:\d+$/, "");
    const port = Number(parsed.port);
    if (!PROXY_SCHEMES.has(parsed.protocol) || !hostname || !parsed.port || !Number.isInteger(port) || port < 1 || port > 65535) return false;
    const userInfo = authority.lastIndexOf("@") >= 0 ? authority.slice(0, authority.lastIndexOf("@")) : "";
    const [username, password] = userInfo ? userInfo.split(":", 2) : ["", ""];
    if (hasExplicitPath || parsed.search || parsed.hash || hostname === "localhost" || /[^\x00-\x7f%]/.test(hostPart) || hostPart.includes("%") || !hasValidPercentEscapes(username) || !hasValidPercentEscapes(password) || isPrivateIpv4(hostname) || isPrivateIpv6(hostname) || (!hostname.includes(":") && (isAmbiguousNumericHost(hostPart) || !hasValidDnsLabels(hostname)))) return false;
    if ((parsed.username && !parsed.password) || (!parsed.username && parsed.password)) return false;
    if ((authority.match(/@/g) ?? []).length > 1) return false;
    return true;
  } catch {
    return false;
  }
}

export function safeProxyDisplay(value: string): string | null {
  if (value === "direct") return value;
  if (!isValidProxyUrl(value)) return null;
  const parsed = new URL(value);
  if (parsed.username || parsed.password) return null;
  const hostname = parsed.hostname.includes(":") ? `[${parsed.hostname.replace(/^\[|\]$/g, "")}]` : parsed.hostname;
  return `${parsed.protocol}//${hostname}:${parsed.port}`;
}
