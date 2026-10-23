# Website assessment and redesign, 2026-10-22

## Baseline and observations (before implementation)

Base: origin/main 7128d5b, not the dirty local index.html. Reviewed all six recent
commit subjects, current HTML/CSS/JS and expanded README. Opened the live www site
in Chrome: the same dark usage-focused site is visible, including 127/127,
100x, simulated terminal output labeled LIVE OUTPUT and hosted-gateway offers.
The browser also applies an external bilingual translation; that overlay is not
assumed to be a source-code defect. Native source i18n nevertheless leaves some
labels, terminal content, hero text and pricing lists outside translation.

Keep: EN/ZH selection, data-i/data-ih approach, workflow explanation, inspectable
gateway examples, project assets, developer documentation and README work.
Change: remove unqualified safety/performance claims, animated fake live activity,
unsupported commercial offers and stale test counts. No customer/volume claims.
The local protocol branch and origin/main are distinct implementations: link
strict-profile evidence to its immutable commit, not pretend it merged to main.

## Information architecture

1. NeuralClear name + clearing-layer proposition; prototype/rail-agnostic boundary.
2. Four-step flow: reserve internal credits, hash-chain meter, net settlement,
   signed receipt. Explain legal custody is provided by licensed partners.
3. Dated evidence: strict-profile code, independent VALID verification, Stripe
   test collection and JPY Transfer, payout pending until Oct 29. Link reports
   to protocol commit 54bd57f; never market test mode as real-money adoption.
4. x402 relationship: HTTP payment execution complements clearing evidence.
   Avoid claiming x402 universally requires one payment per task or cannot batch.
5. Retain gateway example explorer; label examples as examples, not live telemetry.
   Protocol/doc links distinguish main reference implementation from escrow branch.
6. Design-partner CTA via public GitHub issue (no invented email or lead capture).
   Ask for use case/rail/verification requirements, explicitly no sensitive data.
7. Agent entry points: robots.txt, sitemap.xml, llms.txt and JSON agent-skills.

## Visual and implementation plan

Evolve existing static page and responsive layout, retaining interactive endpoint
explorer and EN/ZH mechanism. Quiet graphite/white/green/amber, stable four-step
grid, readable body text, no ticker/scanline or decorative network animation.
No invented product imagery: reuse existing project icon as a brand asset.
Every new prose label has both translations; persist language and set html lang.
Real root files plus a static 404 prevent Cloudflare's implicit SPA fallback;
_headers declares JSON/plain text content types. No production settings changed.

## Verification plan

Check English/Chinese, mobile/desktop, keyboard controls, internal anchors,
local resources and machine-file types/content. Run repository tests and new
static-site tests. Preview only; commit/push website-redesign-2026-10-22, no merge
or production deploy. Public production agent paths remain unfixed until approval.

## Implementation and verification (2026-10-23)

Implemented the sections above in index.html, with readable site.css/site.js.
Retained the seven main-branch gateway examples, native EN/ZH selection and
existing brand image. README and protocol/runtime modules are unchanged.
Added the four actual machine files, _headers and 404.html. Output directory
remains the repository root; no Cloudflare configuration was changed.

Validation: full pytest suite passed with 130 tests and 29 subtests, including
three new website checks. An initial restricted run could not bind local HTTP
ports; the authorized rerun passed. Browser inspection confirmed desktop
English/Chinese content, the language selector and endpoint-example interaction.
Local HTTP returned 200 for all four machine files and CSS/JS; JSON and XML parsed.
Local links and anchors are checked by tests; git diff --check passed.
Responsive CSS is present, but a separate mobile-device visual pass has not been
completed. Cloudflare-specific MIME headers and its 404 behavior still require
a Pages preview check after branch publication; local SimpleHTTPServer does not
interpret _headers. No production deployment or main merge is authorized here.

Review decisions: approve the quieter visual direction, choose whether public
GitHub issues are the desired design-partner contact channel, and decide protocol
branch integration separately. Update the dated payout evidence only after a new
verified outcome; October 29 availability is not a successful-payout claim.
