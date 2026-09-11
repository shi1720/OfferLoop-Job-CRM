/* OfferLoop end-to-end tour.
 *
 * Drives the full UI against a running demo stack, asserts the critical
 * flows, and (optionally) captures the screenshots used in the README.
 *
 * Usage:
 *   make api                     # or: make docker-run (then BASE=http://127.0.0.1:8080)
 *   cd e2e && npm install && npx playwright install chromium
 *   npm run tour                 # assertions only
 *   SHOTS=../docs/screenshots npm run tour   # also refresh screenshots
 *
 * Env:
 *   BASE      target origin           (default http://127.0.0.1:8000)
 *   SHOTS     screenshot directory    (default: none — skip screenshots)
 *   CHROMIUM  explicit browser binary (optional)
 */

const { chromium } = require("playwright");
const fs = require("fs");

const BASE = process.env.BASE || "http://127.0.0.1:8000";
const SHOTS = process.env.SHOTS || "";
const TOAST_SETTLE_MS = 4600; // toasts auto-dismiss at 4.2s — never screenshot over one

const results = [];
function check(name, condition) {
  results.push({ name, ok: Boolean(condition) });
  console.log(`${condition ? "PASS" : "FAIL"}  ${name}`);
}

async function shot(page, name) {
  if (!SHOTS) return;
  await page.screenshot({ path: `${SHOTS}/${name}.png` });
}

(async () => {
  if (SHOTS) fs.mkdirSync(SHOTS, { recursive: true });
  const browser = await chromium.launch(
    process.env.CHROMIUM ? { executablePath: process.env.CHROMIUM } : {},
  );
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 });
  page.on("pageerror", (err) => console.log("PAGE ERROR:", err.message));

  // --- Login ---
  await page.goto(BASE, { waitUntil: "networkidle" });
  check("login page shows brand headline", await page.getByText("Now you won't either.").isVisible());
  await shot(page, "01-login");

  await page.getByRole("button", { name: /Enter OfferLoop/ }).click();
  await page.waitForSelector("text=Pipeline", { timeout: 10000 });
  await page.waitForTimeout(800);

  // --- Board ---
  check(
    "board shows all four stages",
    (await page.locator("section h2").allTextContents()).join().includes("Applied"),
  );
  const cards = await page.locator("[class*='cursor-pointer'][class*='rounded-xl'] p").count();
  check("board renders application cards", cards >= 10);
  await shot(page, "02-pipeline");

  // --- Drawer: open a card and generate a follow-up ---
  await page.getByText("Senior Backend Engineer", { exact: false }).first().click();
  await page.waitForSelector("text=Outreach drafts");
  await page.waitForTimeout(500);
  await shot(page, "03-drawer");

  const draftCountBefore = await page.locator("article").count();
  await page.getByRole("button", { name: /Write cover letter/ }).click();
  await page.waitForTimeout(1200);
  const draftCountAfter = await page.locator("article").count();
  check("generating a cover letter adds a draft", draftCountAfter > draftCountBefore);
  check("provenance chip shows grounding", await page.getByText(/grounded on \d past draft/).first().isVisible());
  await page.waitForTimeout(TOAST_SETTLE_MS);
  await shot(page, "04-drawer-draft");
  await page.keyboard.press("Escape");
  await page.waitForTimeout(400);

  // --- Nudges ---
  await page.getByRole("link", { name: "Nudges" }).click();
  await page.waitForSelector("text=Cadence");
  await page.waitForTimeout(600);
  const nudgeCards = await page.locator("li[class*='rounded-2xl']").count();
  check("nudge inbox has pending nudges", nudgeCards >= 4);
  check("auto-drafted follow-up attached", await page.getByText("Auto-drafted & ready").first().isVisible());
  await shot(page, "05-nudges");

  // --- Import: load samples and run twice (idempotency) ---
  await page.getByRole("link", { name: "Import" }).click();
  await page.waitForSelector("text=Bulk import");
  await page.getByRole("button", { name: /Load sample datasets/ }).click();
  await page.waitForSelector("text=sample_postings.csv");
  await page.getByRole("button", { name: /Run import/ }).click();
  await page.waitForSelector("text=Import report", { timeout: 15000 });
  check("import report rendered", await page.getByText("Linked by jobId").isVisible());
  await page.waitForTimeout(TOAST_SETTLE_MS);
  await shot(page, "06-import");

  // --- Analytics ---
  await page.getByRole("link", { name: "Analytics" }).click();
  await page.waitForSelector("text=Conversion funnel");
  check("analytics shows funnel + weekly momentum", await page.getByText("Weekly momentum").isVisible());
  await page.waitForTimeout(TOAST_SETTLE_MS);
  await shot(page, "07-analytics");

  // --- Profile ---
  await page.getByText("Profile & voice").click();
  await page.waitForSelector("text=grounding context");
  await page.waitForTimeout(400);
  await shot(page, "08-profile");

  await browser.close();

  const failed = results.filter((r) => !r.ok);
  console.log(`\n${results.length - failed.length}/${results.length} tour checks passed`);
  process.exit(failed.length ? 1 : 0);
})().catch((err) => {
  console.error(err);
  process.exit(1);
});
