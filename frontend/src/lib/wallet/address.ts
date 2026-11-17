/** Solana addresses: base58 text for a 32-byte public key. */

const ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz";
const INDEX = new Map([...ALPHABET].map((c, i) => [c, i]));

/** Decoded byte length of a base58 string, or null if it is not base58. */
function base58Length(text: string): number | null {
  const bytes: number[] = [];
  for (const char of text) {
    const value = INDEX.get(char);
    if (value === undefined) return null;
    let carry = value;
    for (let i = 0; i < bytes.length; i++) {
      carry += bytes[i] * 58;
      bytes[i] = carry & 0xff;
      carry >>= 8;
    }
    while (carry > 0) {
      bytes.push(carry & 0xff);
      carry >>= 8;
    }
  }
  let zeros = 0;
  while (zeros < text.length && text[zeros] === "1") zeros++;
  return bytes.length + zeros;
}

/** A well-formed Solana address: base58 that decodes to exactly 32 bytes. */
export function isSolanaAddress(text: string): boolean {
  return text.length >= 32 && text.length <= 44 && base58Length(text) === 32;
}

/** "7xKXtg2C…9fQa" style: enough to recognise, short enough to fit. */
export function shortAddress(address: string, head = 4, tail = 4): string {
  return address.length <= head + tail + 1 ? address : `${address.slice(0, head)}…${address.slice(-tail)}`;
}
