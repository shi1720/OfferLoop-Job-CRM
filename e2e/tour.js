/* OfferLoop end-to-end tour.
 *
 * Drives the full UI against a running demo stack, asserts the critical
 * flows (desktop + a 390px mobile pass), and (optionally) captures the
 * screenshots used in the README.
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

const JD_TEXT =
  "Senior Backend Engineer at Finlo - Python, FastAPI, Bengaluru. We are looking for a " +
  "full-time engineer to own our payments platform, work with PostgreSQL and Kafka, and ship reliably.";

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

  // --- Onboarding tour (auto-starts for fresh profiles) ---
  await page.waitForSelector("text=Start every day here", { timeout: 10000 });
  await page.waitForTimeout(400);
  await shot(page, "09-onboarding");
  const stepTitles = [
    "Your pipeline, on one board",
    "Add a job in seconds",
    "The nudge engine",
    "Nudges arrive pre-written",
    "Bring your whole search",
    "Make it sound like you",
  ];
  let seenAllSteps = true;
  for (const title of stepTitles) {
    await page.getByRole("button", { name: "Next", exact: true }).click();
    await page.waitForTimeout(500); // spotlight glide + possible route change
    if (!(await page.getByText(title).isVisible())) seenAllSteps = false;
  }
  check("onboarding tour walks all seven steps", seenAllSteps);
  await page.getByRole("button", { name: /Start building momentum/ }).click();
  await page.waitForTimeout(600);
  check("tour closes on finish", !(await page.getByText("Skip tour").isVisible()));
  check("momentum chip shows score", await page.getByText(/\d+ momentum/).isVisible());

  // Replay via the "?" button, then skip.
  await page.getByRole("button", { name: "Replay the tour" }).click();
  await page.waitForSelector("text=Start every day here");
  check("tour is replayable from the sidebar", await page.getByText("Skip tour").isVisible());
  await page.getByText("Skip tour").click();
  await page.waitForTimeout(500);

  // --- Today (the landing page) ---
  await page.getByRole("link", { name: "Today", exact: true }).click();
  await page.waitForSelector("text=Due follow-ups");
  check("today greets by name", await page.getByText(/Good (morning|afternoon|evening)/).isVisible());
  check("today shows the weekly goal", await page.getByText(/\/ \d+ applications/).isVisible());
  check("today lists due follow-ups", (await page.locator("text=draft attached").count()) >= 1);
  await page.waitForTimeout(400);
  await shot(page, "10-today");

  // --- Board ---
  await page.getByRole("link", { name: "Pipeline" }).click();
  await page.waitForSelector("text=drag a card");
  await page.waitForTimeout(600);
  check(
    "board shows all four stages",
    (await page.locator("section h2").allTextContents()).join().includes("Applied"),
  );
  const cards = await page.locator("[class*='cursor-pointer'][class*='rounded-xl'] p").count();
  check("board renders application cards", cards >= 10);
  await shot(page, "02-pipeline");

  // --- Quick add: paste a JD, Gemini/regex extracts, modal prefills ---
  await page.getByPlaceholder(/Paste a job link/).fill(JD_TEXT);
  await page.getByRole("button", { name: /Capture/ }).click();
  await page.waitForSelector("text=Confirm captured job", { timeout: 15000 });
  const roleValue = await page.locator("input").nth(1).inputValue().catch(() => "");
  check("quick add prefills the captured role", /Senior Backend Engineer/.test(roleValue));
  await shot(page, "11-quick-add");
  await page.getByLabel("Confirm captured job").getByRole("button", { name: "Log application" }).click();
  await page.waitForTimeout(TOAST_SETTLE_MS);
  check("captured job lands on the board", await page.getByText("Senior Backend Engineer").first().isVisible());

  // --- Drawer: open a card, generate, gmail, prep ---
  await page.getByText("Senior Backend Engineer", { exact: false }).first().click();
  await page.waitForSelector("text=Outreach drafts");
  await page.waitForTimeout(500);
  check("drawer has contact fields", await page.getByPlaceholder("Recruiter / referrer name").isVisible());
  check("drawer offers four draft types", await page.getByText("Request a referral").isVisible());
  await shot(page, "03-drawer");

  const draftCountBefore = await page.locator("article").count();
  await page.getByRole("button", { name: /Write cover letter/ }).click();
  await page.waitForTimeout(1200);
  const draftCountAfter = await page.locator("article").count();
  check("generating a cover letter adds a draft", draftCountAfter > draftCountBefore);
  check("draft can open in Gmail", await page.getByText("Open in Gmail").first().isVisible());

  await page.getByRole("button", { name: /Build prep pack/ }).click();
  await page.waitForSelector("text=Ask them", { timeout: 15000 }); // only exists once the pack renders
  check("interview prep pack renders", await page.getByText("Your stories").isVisible());
  await page.waitForTimeout(TOAST_SETTLE_MS);
  await shot(page, "12-prep-pack");
  await page.keyboard.press("Escape");
  await page.waitForTimeout(400);

  // --- Nudges ---
  await page.getByRole("link", { name: "Nudges" }).click();
  await page.waitForSelector("text=Cadence");
  await page.waitForTimeout(600);
  const nudgeCards = await page.locator("li[class*='rounded-2xl']").count();
  check("nudge inbox has pending nudges", nudgeCards >= 4);
  check("auto-drafted follow-up attached", await page.getByText("Auto-drafted & ready").first().isVisible());
  check("nudges offer a calendar block", await page.getByText("Block time").first().isVisible());
  await shot(page, "05-nudges");

  // --- Import: load samples and run twice (idempotency) ---
  await page.getByRole("link", { name: "Import" }).click();
  await page.waitForSelector("text=Bulk import");
  check("import mentions Teal/Huntr migration", await page.getByText(/Teal or Huntr/).isVisible());
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
  check(
    "follow-up insight present",
    (await page.getByText(/Follow-ups are working|follow-up effect/i).count()) >= 1,
  );
  await page.waitForTimeout(TOAST_SETTLE_MS);
  await shot(page, "07-analytics");

  // --- Profile ---
  await page.getByText("Profile & voice").click();
  await page.waitForSelector("text=grounding context");
  check("AI engine card is present", await page.getByText("AI engine").isVisible());
  check("data export card is present", await page.getByText("Your data").isVisible());
  await page.waitForTimeout(400);
  await shot(page, "08-profile");

  // ======================= Mobile pass (390 × 844) =======================
  const mobile = await browser.newPage({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2 });
  mobile.on("pageerror", (err) => console.log("MOBILE PAGE ERROR:", err.message));
  await mobile.goto(BASE, { waitUntil: "networkidle" });
  await mobile.getByRole("button", { name: /Enter OfferLoop/ }).click();
  await mobile.waitForSelector("text=Due follow-ups", { timeout: 10000 });
  await mobile.waitForTimeout(1200);
  check("mobile: tour stays out of the way", !(await mobile.getByText("Skip tour").isVisible()));
  const overflow = await mobile.evaluate(() => document.body.scrollWidth - window.innerWidth);
  check("mobile: no horizontal body scroll on Today", overflow <= 1);
  await shot(mobile, "13-mobile-today");

  await mobile.getByRole("button", { name: "Open menu" }).click();
  // .last(): the hidden desktop sidebar also carries these — the slide-over copy is last in DOM
  await mobile.getByRole("link", { name: "Pipeline" }).last().waitFor({ state: "visible" });
  check("mobile: menu opens with momentum chip", await mobile.getByText(/\d+ momentum/).last().isVisible());
  await mobile.getByRole("link", { name: "Pipeline" }).last().click();
  await mobile.waitForSelector("text=drag a card");
  await mobile.waitForTimeout(600);
  check("mobile: menu closes after navigating", !(await mobile.getByRole("link", { name: "Analytics" }).last().isVisible()));
  const bodyOverflowBoard = await mobile.evaluate(() => document.body.scrollWidth - window.innerWidth);
  check("mobile: board itself scrolls, body doesn't", bodyOverflowBoard <= 1);
  await shot(mobile, "14-mobile-board");

  await mobile.getByText("Senior Backend Engineer", { exact: false }).first().click();
  await mobile.waitForSelector("text=Outreach drafts");
  await mobile.waitForTimeout(400);
  check("mobile: drawer opens full-width", await mobile.getByText("Interview prep").isVisible());

  await browser.close();

  const failed = results.filter((r) => !r.ok);
  console.log(`\n${results.length - failed.length}/${results.length} tour checks passed`);
  process.exit(failed.length ? 1 : 0);
})().catch((err) => {
  console.error(err);
  process.exit(1);
});
