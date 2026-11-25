/** Word-level diff, used by the panels that show a before/after. */

/** Word-level diff (LCS), capped so huge entries stay fast. Returns [[op, text]] with op "=", "-" or "+". */
export function wordDiff(a, b) {
  const words = (x) => (x || "").match(/\s*\S+\s*/g) || [];   // each word keeps its spaces, so changes never glue words together
  const A = words(a), B = words(b);
  if (A.length * B.length > 400000) return [["-", a], ["+", b]];
  const m = A.length, n = B.length;
  const L = Array.from({ length: m + 1 }, () => new Uint16Array(n + 1));
  for (let i = m - 1; i >= 0; i--) for (let j = n - 1; j >= 0; j--)
    L[i][j] = A[i] === B[j] ? L[i + 1][j + 1] + 1 : Math.max(L[i + 1][j], L[i][j + 1]);
  const out = [];
  const push = (op, t) => { if (out.length && out[out.length - 1][0] === op) out[out.length - 1][1] += t; else out.push([op, t]); };
  let i = 0, j = 0;
  while (i < m && j < n) {
    if (A[i] === B[j]) { push("=", A[i]); i++; j++; }
    else if (L[i + 1][j] >= L[i][j + 1]) push("-", A[i++]);
    else push("+", B[j++]);
  }
  while (i < m) push("-", A[i++]);
  while (j < n) push("+", B[j++]);
  return out;
}
