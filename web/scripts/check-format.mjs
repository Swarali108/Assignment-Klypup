// Tier-1 check for lib/format.ts number output. Run: node --experimental-strip-types scripts/check-format.mjs
import assert from "node:assert/strict";
const f = await import("../lib/format.ts");
assert.equal(f.formatCr(92.05), "₹92.05 Cr");
assert.equal(f.formatCr(1234.5), "₹1,234.50 Cr");
assert.equal(f.formatCr(123456.7), "₹1,23,456.70 Cr");
assert.equal(f.formatCr(null), null);
assert.equal(f.formatINR(12345678), "₹1,23,45,678");
assert.equal(f.formatCount(3810000), "38,10,000");
assert.equal(f.formatDate("2026-11-26"), "26 Nov 2026");
assert.equal(f.formatRelative("2026-11-26", "2026-11-15"), "in 11 days");
assert.equal(f.formatRelative("2026-03-11", "2026-11-15"), "8 months ago");
console.log("format checks passed");
