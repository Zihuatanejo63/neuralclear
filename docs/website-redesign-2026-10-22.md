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

## Third-round positioning correction (2026-10-23)

This direction supersedes the evidence-report tone and the earlier quiet visual
plan above. The site introduces the possibility of agent-to-agent commerce to
design partners, platform founders and investors first; it then makes the
implementation and dated evidence accessible to developers and reviewers.

Narrative: vision -> three possible service-market scenarios -> four-step
clearing loop -> many-to-one netting -> qualitative why-now signal -> built and
verified -> developer entry -> next milestones -> partner/investor invitation.
Keep the approved Hero simulation unchanged. Extend its visual vocabulary with
an explicitly illustrative agent network, a luminous metering chain, converging
streams, a signed-receipt representation, a glass terminal, a milestone path and
a full-width closing field. Section animations are visibility-gated; the four
additional canvases share one scheduler. Static diagrams and prose remain when
JavaScript is unavailable, and reduced-motion users receive static renderings.

Copy rules for subsequent revisions:

- Describe possibilities freely in conditional/future language; do not present
  scenarios or animations as customers, revenue, volume or a live network.
- State verified achievements positively and link to immutable protocol commit
  54bd57f. Published branch evidence is not a claim of integration into main.
- Every Stripe achievement remains explicitly test-mode. The receipt visual
  represents the documented independent VALID result; it does not run a verifier
  in the browser or invent a new receipt, signature or transaction.
- Move future infrastructure and proof work into Next. October 29 is the target
  for attempting/verifying payout after scheduled funds availability, not an
  unconditional promise or a completed-payout claim. Hosted gateway and partner
  integration are planned milestones, not existing commercial offerings.
- Keep the custody boundary accurate: the engine reserves internal credits;
  licensed partners provide real-world custody and compliance.
- All new prose and diagram labels must ship together in EN/ZH. Example API
  payloads remain clearly labeled reference requests, not live output.

Scope: index.html, site.css, site.js and this appended section only. No machine
files, tests, protocol modules, main merge or production deployment are changed.

Validation for this round: 130 pytest tests and 29 subtests passed, including all
three static website tests. Desktop 1440x900 and mobile 390x844 were inspected in
Chrome; the network, clearing chain, netting diagram, receipt, terminal, timeline
and closing field render without horizontal overflow. EN/ZH keys are paired.
A script-blocking CSP check retains all nine sections, seven native example
disclosures and four visible static diagrams. A standalone renderer harness
checks the unchanged Hero function, section visibility/hidden-tab pause,
reduced-motion static rendering, missing-canvas fallback and JS size budget.
