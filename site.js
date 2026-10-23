var EPS = [
  {
    m: "POST",
    p: "/v1/accounts",
    s: "open account",
    c: 'curl -X POST $GW/v1/accounts \\\n  -H "X-NeuralClear-Api-Key: $KEY" \\\n  -d \'{"account":"owner.acme","deposit":200}\'\n\n→ {"account":"owner.acme","balance":200}',
  },
  {
    m: "POST",
    p: "/v1/clear",
    s: "full clearing, one call",
    c: 'curl -X POST $GW/v1/clear -d \'{\n  "buyer_owner": "owner.acme",\n  "provider_url": "http://provider:8001",\n  "capability": "echo.text",\n  "payload": {"msg": "hi"}\n}\'\n\n# gateway: quote → escrow hold → remote HTTP\n# execution → proof → release → signed receipt\n→ {"receipt_id":"rcpt_tx_…","amount":10,"fee":1}',
  },
  {
    m: "POST",
    p: "/v1/channels",
    s: "open netting channel",
    c: 'curl -X POST $GW/v1/channels -d \'{\n  "buyer":"owner.acme",\n  "provider":"agent.embedder",\n  "deposit":120}\'\n\n→ {"channel_id":"chan_8f58…","spendable":117}',
  },
  {
    m: "POST",
    p: "/v1/channels/{id}/meter",
    s: "hash-chained record",
    c: 'curl -X POST $GW/v1/channels/chan_8f58…/meter -d \'{\n  "capability":"embed.text",\n  "amount":1,\n  "payload_hash":"sha256:9f2c…"}\'\n\n→ {"sequence":42,\n   "prev_hash":"d31b…",\n   "record_hash":"77af…"}',
  },
  {
    m: "POST",
    p: "/v1/channels/{id}/settle",
    s: "one net transfer",
    c: 'curl -X POST $GW/v1/channels/chan_8f58…/settle\n\n→ {"tasks_metered":100,\n   "net_to_provider":100,\n   "refunded_to_buyer":17,\n   "protocol_fee":3,\n   "chain_head":"a90c…",\n   "signature":"hmac-sha256:…"}',
  },
  {
    m: "POST",
    p: "/v1/disputes",
    s: "freeze + resolve",
    c: 'curl -X POST $GW/v1/disputes -d \'{\n  "transaction_id":"tx_d4f0…",\n  "raised_by":"owner.acme",\n  "reason":"report never delivered"}\'\n\n# resolutions: refund | slash | split | settle\n# refund moves money BACK — tested, not implied',
  },
  {
    m: "GET",
    p: "/v1/ledger",
    s: "live balances",
    c: 'curl $GW/v1/ledger\n\n→ {"balances":{"owner.acme":356,\n     "agent.research_pro":40,\n     "agent.embedder":100},\n   "fee_pool":4,\n   "escrow_total":0,\n   "total_supply":500}',
  },
];
const EN = {
    scenarioTag: "POSSIBLE SCENARIO",
    receiptCommit: "Published implementation",
    nextBoundary:
      "Alongside these milestones: distributed persistence, execution-proof integrations and licensed custody partnerships. Current signatures authenticate records; TEE/ZK execution verification is a future integration.",
    next3Body:
      "Invite design partners to define a service, its budget policy and a verifiable settlement path.",
    next3: "Connect a real agent workflow.",
    next3Tag: "NEXT / DESIGN PARTNERS",
    next2Body:
      "A hosted developer gateway, with durable records and operational controls, is the next infrastructure milestone.",
    next2: "Make the protocol easier to try.",
    next2Tag: "NEXT / HOSTED GATEWAY",
    next1Body:
      "Funds are scheduled to become available at 08:00 UTC+8. Next: attempt and verify the final test payout. Completion remains subject to Stripe availability and response.",
    next1: "Close the test payout loop.",
    nextDate: "2026-10-29 / TARGET",
    nextTitle: "From a verified chain to shared infrastructure.",
    nextLabel: "07 / NEXT",
    receiptCaption:
      "Independent verification recorded in the linked test report. Visual representation; no verification is running on this page.",
    receiptCheck: "VALID",
    receiptSignature: "Signature",
    receiptAmount: "Internal settlement",
    receiptProtocol: "Protocol",
    receiptTitle: "The outcome carries its evidence.",
    receiptLabel: "SIGNED RECEIPT / TEST-MODE RECORD",
    whyC: "ACCOUNTABILITY",
    whyB: "DELEGATION",
    whyA: "INTENT",
    whyBody:
      "As agents take on actions and delegate to tools and other agents, authorization, metering and settlement need a shared language.",
    whyTitle: "From answering questions to commissioning work.",
    whyLabel: "04 / WHY NOW",
    sceneCaption:
      "An illustration of agents exchanging work, not a live network.",
    illustration: "ILLUSTRATION / NOT TRANSACTION DATA",
    scenario3Body:
      "Agents could coordinate services around the clock, within owner-defined limits and with an auditable record.",
    scenario3: "Commerce without office hours.",
    scenario2Body:
      "Independent services could be metered per use, with many small actions reconciled into one net settlement.",
    scenario2: "A market for every call.",
    scenario1Body:
      "A research agent could buy a specialist dataset and hire compute on demand, with a budget attached to every delegation.",
    scenario1: "Data meets compute.",
    possIntro:
      "Imagine agents that can discover expertise, commission work and settle the outcome. A shared clearing language could make that cooperation composable.",
    possTitle: "An economy of agents. Working for each other.",
    possLabel: "01 / THE POSSIBILITY",
    engine: "CLEARING ENGINE FOR AGENT SERVICES",
    rail: "RAIL-AGNOSTIC · EST. 2026",
    sequence: "ESCROW — METER — NET — SETTLE",
    scroll: "Scroll to explore",
    example: "EXAMPLE / NOT LIVE",
    verifyWord: "VERIFY",
    netWord: "NET",
    s1: "Possibility",
    s2: "Built & verified",
    s3: "Developers",
    s4: "OPEN PROTOCOL / DEVELOPER PREVIEW",
    s5: "When every agent can hire another, commerce needs a neutral clearing layer.",
    s6: "Reserve credits. Meter work. Settle net. Verify the receipt. A rail-agnostic evidence layer, not another payment rail.",
    s7: "Build what comes next",
    s8: "Read the specification",
    s9: "Internal escrow reserves credits. Licensed partners provide real-world custody and compliance.",
    s10: "02 / HOW IT WORKS",
    s11: "Work happens in steps. Trust follows the chain.",
    s12: "Reserve",
    s13: "A mandate bounds spending; escrow reserves the agreed internal credits.",
    s14: "Meter",
    s15: "Each accepted entry links to its predecessor. Changes break the hash chain.",
    s16: "Settle net",
    s17: "Allocate metered charges and fees; return unused credits under the policy.",
    s18: "Sign & verify",
    s19: "Verify the receipt and metering chain without running a ledger.",
    s20: "Signed receipts and Merkle proofs make the record independently verifiable.",
    s21: "05 / BUILT & VERIFIED",
    s22: "An idea you can inspect. Evidence you can verify.",
    s23: "Published protocol work at commit 54bd57f. The Stripe evidence below is from test mode.",
    s24: "Strict escrow-v1, implemented",
    s25: "A working state machine, independent verifier, signed mandates and Merkle proofs. Inspect the published implementation.",
    s26: "Explore the protocol",
    s27: "A receipt, independently verified",
    s28: "Stripe test collection → internal escrow → metering → net settlement → signed receipt. Independent verification returned VALID.",
    s29: "Read the verification record",
    s30: "Stripe test Transfer, created",
    s31: "USD 0.50 became JPY 79 gross − JPY 6 fee = JPY 73 net. The test Transfer was created; the payout step follows funds availability.",
    s32: "Read the test-chain evidence",
    s33: "03 / MANY ACTIONS. ONE NET RESULT.",
    s34: "Meter the work. Move the net.",
    s35: "HTTP-native payment requirements and execution around a request.",
    s36: "x402 documentation",
    s37: "Verifiable metering turns many service actions into a net allocation, with signed evidence. A complementary layer above payment rails.",
    s38: "Rail-agnostic by design: choose the payment rail, keep the clearing evidence.",
    s39: "06 / BUILD WITH IT",
    s40: "An open protocol. A place to start.",
    s41: "Explore the gateway request examples, read the specification and bring your own agent workflow.",
    s42: "Specification",
    s43: "Protocol documents",
    s44: "Request examples from the reference implementation. Run them against your own gateway.",
    s45: "08 / BUILD THE NEXT LAYER",
    s46: "What could your agents do together?",
    s47: "For design partners, agent-platform founders and investors: help shape the clearing layer for agent-to-agent commerce. Start with one service, one budget and one verifiable outcome.",
    s48: "Start a conversation",
    s49: "Opens a public GitHub issue. Describe your use case; keep credentials, personal data and customer information private.",
    s50: "Open clearing protocol prototype. Built for the possibilities ahead.",
  },
  ZH = {
    scenarioTag: "愿景场景",
    receiptCommit: "已发布实现",
    nextBoundary:
      "同步推进的方向：分布式持久化、执行证明集成及持牌托管合作。当前签名认证记录，TEE/ZK 执行验证属于后续集成。",
    next3Body: "邀请设计伙伴共同定义服务、预算策略与可验证的结算路径。",
    next3: "接入一个真实的 Agent 工作流。",
    next3Tag: "下一步 / 设计伙伴",
    next2Body:
      "面向开发者的托管网关，配合持久化记录与运维控制，是下一阶段的基础设施目标。",
    next2: "让协议更容易被体验。",
    next2Tag: "下一步 / 托管网关",
    next1Body:
      "资金预计于 08:00（UTC+8）可用。接下来尝试并验证最后一步测试 payout；是否完成取决于 Stripe 资金状态与返回结果。",
    next1: "完成测试出金闭环。",
    nextDate: "2026-10-29 / 计划节点",
    nextTitle: "从可验证链路，走向共享基础设施。",
    nextLabel: "07 / 接下来",
    receiptCaption:
      "独立验证结果见关联测试报告。此处为视觉呈现，页面未实时执行验证。",
    receiptCheck: "VALID",
    receiptSignature: "签名",
    receiptAmount: "内部结算",
    receiptProtocol: "协议",
    receiptTitle: "让成果，自带证据。",
    receiptLabel: "签名收据 / 测试模式记录",
    whyC: "可追溯",
    whyB: "委托",
    whyA: "意图",
    whyBody:
      "当 Agent 开始执行动作、调用工具、委托其他 Agent，授权、计量与结算就需要一种共同语言。",
    whyTitle: "从回答问题，走向委托工作。",
    whyLabel: "04 / 为什么现在",
    sceneCaption: "Agent 间工作交换的示意，并非实时网络。",
    illustration: "示意 / 非交易数据",
    scenario3Body:
      "Agent 可以全天候协调服务，在所有者设定的额度内行动，并留下可审计的记录。",
    scenario3: "商业协作，不止于工作时间。",
    scenario2Body: "独立服务可以按次计量，多笔微小动作汇为一次净额结算。",
    scenario2: "每次调用，都可以成为市场。",
    scenario1Body:
      "研究 Agent 可以购买专业数据，按需雇佣算力，每次委托都携带明确预算。",
    scenario1: "让数据遇见算力。",
    possIntro:
      "想象 Agent 能发现专业能力、委托工作、结算成果。共同的清算语言，可以让这种协作自由组合。",
    possTitle: "Agent 之间，也可以彼此雇佣。",
    possLabel: "01 / 可能性",
    engine: "面向 AGENT 服务的清算引擎",
    rail: "轨道无关 · 始于 2026",
    sequence: "托管 — 计量 — 净额 — 结算",
    scroll: "向下探索",
    example: "请求示例 / 非实时数据",
    verifyWord: "验证",
    netWord: "净额",
    s1: "可能性",
    s2: "已建成并验证",
    s3: "开发者",
    s4: "开放协议 / 开发者预览",
    s5: "当每个 Agent 都能雇佣其他 Agent，交易需要一个中立的清算层。",
    s6: "预付保留积分、计量工作、净额结算、验证收据。不绑定支付轨道的证据层，而非另一个支付通道。",
    s7: "一起构建下一步",
    s8: "阅读协议规范",
    s9: "内部 escrow 预留积分；真实资金托管与合规由持牌合作方提供。",
    s10: "02 / 如何运作",
    s11: "工作逐步完成，信任沿链传递。",
    s12: "预付托管",
    s13: "通过 mandate 限定支出，将约定积分预留在内部 escrow。",
    s14: "哈希链计量",
    s15: "每条认可的计量记录关联前一条记录，篡改会破坏哈希链。",
    s16: "净额结算",
    s17: "按计量结果分配服务款与费用，按策略退回剩余积分。",
    s18: "签名与验证",
    s19: "无需运行账本，即可独立验证收据与计量链。",
    s20: "签名收据与 Merkle 证明，让记录可被独立验证。",
    s21: "05 / 已建成并验证",
    s22: "理念可以审阅，证据可以验证。",
    s23: "协议成果已发布于提交 54bd57f。下方 Stripe 证据均来自测试模式。",
    s24: "严格 escrow-v1 已实现",
    s25: "状态机、独立验证器、签名授权与 Merkle 证明已落地。公开实现可供审阅。",
    s26: "探索协议实现",
    s27: "一份独立验真的收据",
    s28: "Stripe 测试入金 → 内部托管 → 计量 → 净额结算 → 签名收据，独立验证返回 VALID。",
    s29: "阅读验证记录",
    s30: "Stripe 测试 Transfer 已创建",
    s31: "USD 0.50 换汇为 JPY 79 毛额 − JPY 6 手续费 = JPY 73 净额。测试 Transfer 已创建，资金可用后进入 payout 步骤。",
    s32: "阅读测试链路证据",
    s33: "03 / 多次执行，一个净额",
    s34: "逐次计量，净额流转。",
    s35: "围绕 HTTP 请求表达支付要求并执行支付。",
    s36: "x402 文档",
    s37: "可验证计量将多次服务执行归为附带签名证据的净额分配。它是支付轨道之上的互补层。",
    s38: "架构不绑定支付轨道：选择你的通道，保留共同的清算证据。",
    s39: "06 / 开始构建",
    s40: "开放的协议，共同的起点。",
    s41: "探索网关请求示例，阅读规范，带入你自己的 Agent 工作流。",
    s42: "规范",
    s43: "协议文档",
    s44: "以上为参考实现的请求示例，请连接你自己的网关运行。",
    s45: "08 / 共建下一层",
    s46: "你的 Agent，能一起做什么？",
    s47: "面向设计伙伴、Agent 平台创始人与投资人：共同塑造 Agent 间商业协作的清算层。从一种服务、一份预算、一个可验证的结果开始。",
    s48: "开启对话",
    s49: "将打开公开 GitHub Issue。请描述使用场景，勿提交密钥、个人信息或客户机密。",
    s50: "开放清算协议原型，为下一种可能而构建。",
  };
const EPZH = [
  "开户",
  "一次请求清算",
  "开通净额通道",
  "哈希链计量",
  "净额结算",
  "争议处理",
  "账本余额",
];
let LANG = "en",
  ec = 0;
const motion = matchMedia("(prefers-reduced-motion: reduce)");
let typingTimer = 0;
function showExample(animate) {
  clearTimeout(typingTimer);
  const output = document.getElementById("epcode");
  const text = EPS[ec].c;
  if (!animate || motion.matches || document.hidden) {
    output.textContent = text;
    return;
  }
  let count = 0;
  const start = performance.now();
  function type() {
    count = Math.min(
      text.length,
      Math.ceil((performance.now() - start) * 0.65),
    );
    output.textContent = text.slice(0, count);
    if (count < text.length) typingTimer = setTimeout(type, 24);
  }
  type();
}
function re(animate = false) {
  document.querySelectorAll(".ep").forEach((x, i) => {
    x.classList.toggle("act", i === ec);
    x.setAttribute("aria-pressed", String(i === ec));
  });
  showExample(animate);
}
document.getElementById("eplist").replaceChildren();
EPS.forEach((e, i) => {
  let b = document.createElement("button");
  b.className = "ep";
  b.type = "button";
  let p = document.createElement("span");
  p.textContent = e.m + " " + e.p;
  let s = document.createElement("small");
  b.append(p, s);
  b.onclick = () => {
    ec = i;
    re(true);
  };
  document.getElementById("eplist").append(b);
});
function setLang(l) {
  LANG = l === "zh" ? "zh" : "en";
  document.documentElement.lang = LANG === "zh" ? "zh-CN" : "en";
  document.getElementById("lang").value = LANG;
  const D = LANG === "zh" ? ZH : EN;
  document
    .querySelectorAll("[data-i]")
    .forEach((el) => (el.textContent = D[el.dataset.i]));
  document
    .querySelectorAll(".ep small")
    .forEach((s, i) => (s.textContent = LANG === "zh" ? EPZH[i] : EPS[i].s));
  try {
    localStorage.setItem("neuralclear-language", LANG);
  } catch {}
  re();
}
document.getElementById("lang").onchange = (e) => setLang(e.target.value);
// Keyboard selection/copy never waits for the illustrative typing effect.
document
  .getElementById("epcode")
  .addEventListener("focus", () => showExample(false));
let initial = "en";
try {
  initial = localStorage.getItem("neuralclear-language") || "en";
} catch {}
setLang(initial);

// Atmosphere only. No transaction feed or financial state enters this renderer.
(function flowField() {
  const canvas = document.getElementById("flow-field");
  const ctx = canvas.getContext("2d", { alpha: false });
  if (!ctx) return;
  const hero = document.getElementById("hero");
  const capacity = 10000;
  const x = new Float32Array(capacity),
    y = new Float32Array(capacity);
  const vx = new Float32Array(capacity),
    vy = new Float32Array(capacity);
  const anchor = new Float32Array(24);
  let w = 1,
    h = 1,
    count = 10000,
    raf = 0,
    last = 0,
    elapsed = 0,
    slow = 0;
  let px = 0,
    py = 0,
    touched = -100,
    shiftX = 0,
    shiftY = 0,
    visible = true,
    previousPulse = 0;
  function resize() {
    w = hero.clientWidth;
    h = hero.clientHeight;
    const dpr = Math.min(devicePixelRatio || 1, 1.75);
    canvas.width = Math.round(w * dpr);
    canvas.height = Math.round(h * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    count = w <= 768 ? 800 : capacity;
    for (let i = 0; i < capacity; i++) {
      x[i] = Math.random() * w;
      y[i] = Math.random() * h;
      vx[i] = Math.cos(i) * 1.5;
      vy[i] = Math.sin(i) * 1.5;
    }
    ctx.globalCompositeOperation = "source-over";
    ctx.globalAlpha = 1;
    ctx.fillStyle = "#101313";
    ctx.fillRect(0, 0, w, h);
    render(1, 0);
    schedule();
  }
  // All state and chain anchors are allocated once. Two batched paths avoid
  // per-particle canvas state changes; the flow has no positional band target.
  function render(dt, t) {
    const phase = t % 10;
    const pulse = phase > 8.4 ? Math.sin(((phase - 8.4) / 1.6) * Math.PI) : 0;
    const released = previousPulse > 0 && pulse === 0;
    previousPulse = pulse;
    if (t - touched > 5) {
      px = w * (0.5 + 0.36 * Math.sin(t * 0.23));
      py = h * (0.5 + 0.34 * Math.sin(t * 0.31 + 0.8));
    }
    shiftX += ((0.5 - px / w) * 28 - shiftX) * 0.035 * dt;
    shiftY += ((0.5 - py / h) * 28 - shiftY) * 0.035 * dt;
    ctx.globalCompositeOperation = "source-over";
    ctx.globalAlpha = 0.16;
    ctx.fillStyle = "#101313";
    ctx.fillRect(0, 0, w, h);
    ctx.globalCompositeOperation = "lighter";
    for (let j = 0; j < 24; j++)
      anchor[j] =
        h * (0.44 + 0.08 * Math.sin(j * 0.43 + t * 0.18) + 0.016 * (j % 2));
    for (let layer = 0; layer < 2; layer++) {
      ctx.lineWidth = layer ? 1.65 : 0.65;
      ctx.strokeStyle = pulse > 0.3 ? "#effff5" : "#99e5bb";
      ctx.globalAlpha = (layer ? 0.64 : 0.24) + pulse * 0.3;
      ctx.beginPath();
      for (let i = layer; i < count; i += 2) {
        const ox = x[i],
          oy = y[i];
        const angle =
          Math.sin((ox / w) * 6.4 + t * 0.16) * 2.4 +
          Math.cos((oy / h) * 5.2 - t * 0.19) * 2.1 +
          Math.sin((ox / w + oy / h) * 4 - t * 0.11);
        const speed = layer ? 0.72 : 1.8;
        let ax = (Math.cos(angle) * speed - vx[i]) * 0.045;
        let ay = (Math.sin(angle) * speed - vy[i]) * 0.045;
        const dx = ox - px,
          dy = oy - py,
          d = dx * dx + dy * dy;
        if (d < 32400 && d > 1) {
          const f = (1 - d / 32400) * 0.0025;
          ax += (dx - dy * 0.85) * f;
          ay += (dy + dx * 0.85) * f;
        }
        if (pulse > 0) {
          const u = Math.max(0, Math.min(22.999, (ox / w) * 23)),
            j = u | 0;
          const target = anchor[j] + (anchor[j + 1] - anchor[j]) * (u - j);
          ay += (target - oy) * pulse * 0.028 - vy[i] * pulse * 0.12;
          ax += pulse * 0.12;
        }
        if (released) {
          vx[i] += Math.cos(i * 2.399) * 4;
          vy[i] += Math.sin(i * 2.399) * 14;
        }
        vx[i] += ax * dt;
        vy[i] += ay * dt;
        x[i] += vx[i] * dt;
        y[i] += vy[i] * dt;
        if (x[i] < 0 || x[i] > w || y[i] < 0 || y[i] > h) {
          x[i] = (x[i] + w) % w;
          y[i] = (y[i] + h) % h;
        } else {
          ctx.moveTo(ox + shiftX, oy + shiftY);
          ctx.lineTo(x[i] + shiftX + 0.55, y[i] + shiftY + 0.25);
        }
      }
      ctx.stroke();
    }
    if (pulse > 0) {
      ctx.beginPath();
      for (let j = 0; j < 24; j++) {
        if (j === 0) ctx.moveTo(0, anchor[j] + shiftY);
        else ctx.lineTo((j * w) / 23, anchor[j] + shiftY);
      }
      ctx.strokeStyle = "#99e5bb";
      ctx.globalAlpha = pulse * 0.16;
      ctx.lineWidth = 14;
      ctx.stroke();
      ctx.globalAlpha = pulse * 0.9;
      ctx.strokeStyle = "#effff5";
      ctx.lineWidth = 2;
      ctx.stroke();
    }
    ctx.globalAlpha = 1;
    ctx.globalCompositeOperation = "source-over";
  }
  function frame(now) {
    raf = 0;
    if (document.hidden || !visible || motion.matches) {
      last = 0;
      return;
    }
    const raw = last ? now - last : 16.667,
      ms = Math.min(raw, 40);
    last = now;
    elapsed += ms / 1000;
    slow = raw > 1000 / 45 ? slow + 1 : Math.max(0, slow - 1);
    if (slow > 90) {
      count = Math.max(w <= 768 ? 400 : 3000, count - 1000);
      slow = 0;
    }
    render(ms / 16.667, elapsed);
    raf = requestAnimationFrame(frame);
  }
  function schedule() {
    cancelAnimationFrame(raf);
    raf = 0;
    last = 0;
    if (!motion.matches && !document.hidden && visible)
      raf = requestAnimationFrame(frame);
  }
  hero.addEventListener(
    "pointermove",
    function (e) {
      if (e.pointerType === "touch") return;
      const rect = hero.getBoundingClientRect();
      px = e.clientX - rect.left;
      py = e.clientY - rect.top;
      touched = elapsed;
    },
    { passive: true },
  );
  if ("IntersectionObserver" in window)
    new IntersectionObserver(function (entries) {
      visible = entries[0].isIntersecting;
      schedule();
    }).observe(hero);
  document.addEventListener("visibilitychange", schedule);
  motion.addEventListener("change", resize);
  window.addEventListener("resize", resize, { passive: true });
  resize();
})();

(function scrollStory() {
  const pipe = document.querySelector(".pipe"),
    svg = document.querySelector(".flow-chain");
  const base = svg.querySelector(".chain-base"),
    lit = svg.querySelector(".chain-lit");
  const steps = document.querySelectorAll(".ps"),
    progress = document.getElementById("scroll-progress");
  let length = 1,
    scheduled = false;
  function layout() {
    const box = pipe.getBoundingClientRect();
    let path = "";
    steps.forEach(function (step, i) {
      const r = step.getBoundingClientRect();
      const x = r.left - box.left + 8,
        y = r.top - box.top + 20;
      path += (i ? " L " : "M ") + x + " " + y;
    });
    svg.setAttribute("viewBox", "0 0 " + box.width + " " + box.height);
    base.setAttribute("d", path);
    lit.setAttribute("d", path);
    length = lit.getTotalLength();
    lit.style.strokeDasharray = length;
    update();
  }
  function update() {
    scheduled = false;
    const box = pipe.getBoundingClientRect();
    const p = motion.matches
      ? 1
      : Math.max(0, Math.min(1, (innerHeight * 0.75 - box.top) / box.height));
    lit.style.strokeDashoffset = length * (1 - p);
    steps.forEach(function (step) {
      step.classList.toggle(
        "active",
        motion.matches || step.getBoundingClientRect().top < innerHeight * 0.75,
      );
    });
    const max = document.documentElement.scrollHeight - innerHeight;
    progress.textContent =
      Math.round(max > 0 ? (scrollY / max) * 100 : 0) + "%";
  }
  function request() {
    if (!scheduled) {
      scheduled = true;
      requestAnimationFrame(update);
    }
  }
  if ("IntersectionObserver" in window) {
    const reveal = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (e) {
          if (e.isIntersecting) {
            e.target.classList.remove("pending");
            reveal.unobserve(e.target);
          }
        });
      },
      { threshold: 0.08 },
    );
    document.querySelectorAll(".sec:not(#loop) .wrap").forEach(function (el) {
      el.classList.add("reveal");
      if (!motion.matches && el.getBoundingClientRect().top > innerHeight)
        el.classList.add("pending");
      reveal.observe(el);
    });
  }
  window.addEventListener("scroll", request, { passive: true });
  window.addEventListener("resize", layout, { passive: true });
  document.getElementById("lang").addEventListener("change", layout);
  motion.addEventListener("change", layout);
  if (document.fonts) document.fonts.ready.then(layout);
  layout();
})();

// Below-the-fold scenes share one scheduler; observers keep offscreen work idle.
// These diagrams describe possible relationships, never financial telemetry.
(function sectionScenes() {
  const nodes = new Float32Array([
    0.08, 0.5, 0.22, 0.18, 0.39, 0.58, 0.54, 0.17, 0.73, 0.53, 0.91, 0.22, 0.25,
    0.83, 0.59, 0.85, 0.93, 0.81,
  ]);
  const links = new Uint8Array([
    0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 0, 6, 6, 2, 2, 7, 7, 4, 4, 8, 1, 3, 6, 7, 3,
    7,
  ]);
  const scenes = [];
  const sections = document.querySelectorAll(".sec");
  let raf = 0,
    last = 0,
    time = 0,
    slow = 0,
    quality = 1;
  document.querySelectorAll(".section-scene").forEach(function (canvas) {
    const ctx = canvas.getContext("2d", { alpha: true });
    if (!ctx) return;
    const s = {
      canvas,
      ctx,
      kind: canvas.dataset.scene,
      visible: false,
      w: 1,
      h: 1,
      x: new Float32Array(1600),
      y: new Float32Array(1600),
      count: 1600,
      nx: new Float32Array(9),
      ny: new Float32Array(9),
    };
    scenes.push(s);
    canvas.parentElement.classList.add("canvas-ready");
  });
  function resize() {
    scenes.forEach(function (s) {
      const r = s.canvas.parentElement.getBoundingClientRect(),
        dpr = Math.min(devicePixelRatio || 1, 1.75);
      s.w = r.width;
      s.h = r.height;
      s.count = innerWidth <= 768 ? 650 : 1600;
      s.canvas.width = Math.round(s.w * dpr);
      s.canvas.height = Math.round(s.h * dpr);
      s.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      for (let i = 0; i < 1600; i++) {
        s.x[i] = Math.random() * s.w;
        s.y[i] = Math.random() * s.h;
      }
      draw(s, 0, 1);
    });
    schedule();
  }
  function draw(s, t, dt) {
    const c = s.ctx,
      w = s.w,
      h = s.h;
    c.clearRect(0, 0, w, h);
    c.strokeStyle = "#99e5bb";
    c.fillStyle = "#bafbd7";
    if (s.kind === "network") {
      for (let i = 0; i < 9; i++) {
        s.nx[i] = (nodes[i * 2] + Math.sin(t * 0.24 + i) * 0.018) * w;
        s.ny[i] = (nodes[i * 2 + 1] + Math.cos(t * 0.31 + i) * 0.025) * h;
      }
      c.lineWidth = 1;
      c.globalAlpha = 0.27;
      c.beginPath();
      for (let i = 0; i < links.length; i += 2) {
        const a = links[i],
          b = links[i + 1];
        c.moveTo(s.nx[a], s.ny[a]);
        c.lineTo(s.nx[b], s.ny[b]);
      }
      c.stroke();
      for (let i = 0; i < links.length; i += 2) {
        const a = links[i],
          b = links[i + 1],
          p = (Math.sin(t * 0.7 + i) + 1) * 0.5;
        const x = s.nx[a] + (s.nx[b] - s.nx[a]) * p,
          y = s.ny[a] + (s.ny[b] - s.ny[a]) * p;
        c.globalAlpha = 0.12;
        c.beginPath();
        c.arc(x, y, 9, 0, Math.PI * 2);
        c.fill();
        c.globalAlpha = 0.9;
        c.beginPath();
        c.arc(x, y, 2.2, 0, Math.PI * 2);
        c.fill();
      }
      for (let i = 0; i < 9; i++) {
        c.globalAlpha = 0.1;
        c.beginPath();
        c.arc(s.nx[i], s.ny[i], 22, 0, Math.PI * 2);
        c.fill();
        c.globalAlpha = 0.85;
        c.beginPath();
        c.arc(s.nx[i], s.ny[i], 4, 0, Math.PI * 2);
        c.fill();
        c.globalAlpha = 0.32;
        c.beginPath();
        c.arc(s.nx[i], s.ny[i], 13, 0, Math.PI * 2);
        c.stroke();
      }
    } else if (s.kind === "net") {
      for (let j = 0; j < 9; j++) {
        c.globalAlpha = 0.17;
        c.lineWidth = 1;
        c.beginPath();
        const sy = h * (0.1 + j * 0.1);
        c.moveTo(w * 0.02, sy);
        c.bezierCurveTo(w * 0.38, sy, w * 0.45, h * 0.5, w * 0.67, h * 0.5);
        c.stroke();
        for (let k = 0; k < 6; k++) {
          const p = (t * 0.13 + k / 6 + j * 0.063) % 1,
            q = 1 - p;
          const x =
            (q * q * q * 0.02 +
              3 * q * q * p * 0.38 +
              3 * q * p * p * 0.45 +
              p * p * p * 0.67) *
            w;
          const y =
            q * q * q * sy +
            3 * q * q * p * sy +
            3 * q * p * p * h * 0.5 +
            p * p * p * h * 0.5;
          c.globalAlpha = 0.5;
          c.beginPath();
          c.arc(x, y, 1.6, 0, Math.PI * 2);
          c.fill();
        }
      }
      c.globalAlpha = 0.15;
      c.lineWidth = 16;
      c.beginPath();
      c.moveTo(w * 0.67, h * 0.5);
      c.lineTo(w * 0.98, h * 0.5);
      c.stroke();
      c.globalAlpha = 0.9;
      c.lineWidth = 3;
      c.stroke();
      for (let i = 0; i < 6; i++) {
        const p = (t * 0.21 + i / 6) % 1;
        c.fillRect(w * (0.67 + p * 0.3), h * 0.5 - 3, 8, 6);
      }
    } else {
      const n = Math.floor(s.count * quality);
      c.globalAlpha = s.kind === "chain" ? 0.3 : 0.65;
      c.lineWidth = 0.8;
      c.beginPath();
      for (let i = 0; i < n; i++) {
        const x = s.x[i],
          y = s.y[i];
        const a =
          Math.sin((x / w) * 6 + t * 0.12) * 2 +
          Math.cos((y / h) * 5 - t * 0.13) * 2;
        s.x[i] += Math.cos(a) * dt * (i % 2 ? 0.65 : 1.6);
        s.y[i] += Math.sin(a) * dt * (i % 2 ? 0.65 : 1.6);
        if (s.x[i] < 0 || s.x[i] > w || s.y[i] < 0 || s.y[i] > h) {
          s.x[i] = (s.x[i] + w) % w;
          s.y[i] = (s.y[i] + h) % h;
        } else {
          c.moveTo(x, y);
          c.lineTo(s.x[i] + 2, s.y[i] + 0.6);
        }
      }
      c.stroke();
    }
    c.globalAlpha = 1;
  }
  function frame(now) {
    raf = 0;
    if (document.hidden || motion.matches) return;
    const raw = last ? now - last : 16.667,
      dt = Math.min(raw, 40) / 16.667;
    last = now;
    time += Math.min(raw, 40) / 1000;
    slow = raw > 1000 / 45 ? slow + 1 : Math.max(0, slow - 1);
    if (slow > 90) {
      quality = Math.max(0.35, quality - 0.15);
      slow = 0;
    }
    let active = false;
    for (let i = 0; i < scenes.length; i++)
      if (scenes[i].visible) {
        draw(scenes[i], time, dt);
        active = true;
      }
    if (active) raf = requestAnimationFrame(frame);
  }
  function schedule() {
    cancelAnimationFrame(raf);
    raf = 0;
    last = 0;
    if (!document.hidden && !motion.matches && scenes.some((s) => s.visible))
      raf = requestAnimationFrame(frame);
  }
  if ("IntersectionObserver" in window) {
    const observer = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (e) {
          e.target.classList.toggle(
            "scene-on",
            e.isIntersecting && !document.hidden && !motion.matches,
          );
          scenes.forEach(function (s) {
            if (s.canvas.closest(".sec") === e.target)
              s.visible = e.isIntersecting;
          });
        });
        schedule();
      },
      { threshold: 0 },
    );
    sections.forEach((s) => observer.observe(s));
  }
  document.addEventListener("visibilitychange", function () {
    sections.forEach(function (s) {
      if (document.hidden) s.classList.remove("scene-on");
    });
    if (!document.hidden)
      sections.forEach(function (s) {
        const r = s.getBoundingClientRect();
        s.classList.toggle(
          "scene-on",
          r.bottom > 0 && r.top < innerHeight && !motion.matches,
        );
      });
    schedule();
  });
  motion.addEventListener("change", function () {
    sections.forEach(function (s) {
      const r = s.getBoundingClientRect();
      s.classList.toggle(
        "scene-on",
        !motion.matches &&
          !document.hidden &&
          r.bottom > 0 &&
          r.top < innerHeight,
      );
    });
    resize();
  });
  window.addEventListener("resize", resize, { passive: true });
  resize();
})();

document.addEventListener("visibilitychange", function () {
  if (document.hidden) showExample(false);
});
motion.addEventListener("change", function () {
  showExample(false);
});
