const test = require("node:test");
const assert = require("node:assert");
const { hostOf, isBlocked, remaining, fmt } = require("../extension/lib.js");

const list = ["youtube.com", "instagram.com", "x.com"];
test("blockt Domains und Subdomains", () => {
  assert.ok(isBlocked("https://www.youtube.com/watch?v=1", list));
  assert.ok(isBlocked("https://m.youtube.com/", list));
  assert.ok(isBlocked("http://instagram.com", list));
  assert.ok(isBlocked("https://x.com/home", list));
});
test("blockt keine ähnlichen oder internen Seiten", () => {
  assert.ok(!isBlocked("https://notyoutube.com/", list));
  assert.ok(!isBlocked("https://wikipedia.org/x", list));
  assert.ok(!isBlocked("chrome://settings", list));
  assert.ok(!isBlocked("chrome-extension://abc/blocked.html", list));
  assert.ok(!isBlocked("kaputt", list));
  assert.ok(!isBlocked("https://x.com.evil.example/", list));
  assert.strictEqual(hostOf("https://WWW.Foo.com/a"), "foo.com");
});
test("remaining zählt lokal weiter", () => {
  const s = { active: true, remaining: 100, fetchedAt: 1000 };
  assert.strictEqual(remaining(s, 31000), 70);
  assert.strictEqual(remaining(s, 500000), 0);
  assert.strictEqual(remaining({ active: false, remaining: 5, fetchedAt: 0 }, 0), 0);
  assert.strictEqual(fmt(125), "2:05");
});
