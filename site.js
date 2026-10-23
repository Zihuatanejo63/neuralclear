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
    scroll: "Scroll to explore",
    example: "EXAMPLE / NOT LIVE",
    verifyWord: "VERIFY",
    netWord: "NET",
    s1: "Flow",
    s2: "Evidence",
    s3: "Developers",
    s4: "OPEN PROTOCOL / DEVELOPER PREVIEW",
    s5: "The clearing layer for agent-to-agent payments.",
    s6: "Reserve credits. Meter work. Settle net. Verify the receipt. A rail-agnostic evidence layer, not another payment rail.",
    s7: "Explore a design partnership",
    s8: "Read the specification",
    s9: "Prototype. Internal escrow is a ledger reservation, not legal custody. Licensed partners must handle custody and compliance.",
    s10: "01 / CLEARING FLOW",
    s11: "From authorized work to auditable settlement.",
    s12: "Reserve",
    s13: "A mandate bounds spending; escrow reserves the agreed internal credits.",
    s14: "Meter",
    s15: "Each accepted entry links to its predecessor. Changes break the hash chain.",
    s16: "Settle net",
    s17: "Allocate metered charges and fees; return unused credits under the policy.",
    s18: "Sign & verify",
    s19: "Verify the receipt and metering chain without running a ledger.",
    s20: "Integrity is not truth: signatures and Merkle proofs authenticate records, not service quality. TEE/ZK execution verification is not implemented.",
    s21: "02 / EVIDENCE · 2026-10-22",
    s22: "What is demonstrated. What is still open.",
    s23: "This evidence belongs to protocol commit 54bd57f, not yet merged into main. Test mode is not production payment activity.",
    s24: "Strict escrow-v1 / opt-in",
    s25: "State machine, independent verifier, signed mandates and Merkle proofs. Evidence-bound quorum decisions still depend on trusted signers.",
    s26: "Inspect dated evidence",
    s27: "Signed receipt / test mode",
    s28: "Stripe collection → internal escrow → metering → net settlement → signed receipt. Independent verification returned VALID. No customer or volume claims.",
    s29: "Inspect dated evidence",
    s30: "Transfer created / payout pending",
    s31: "USD 0.50 became JPY 79 gross − JPY 6 fee = JPY 73 net. A test Transfer exists. Payout was rejected for pending funds. Available_on: 2026-10-29 08:00 UTC+8; not a promise of completed payout.",
    s32: "Inspect dated evidence",
    s33: "03 / COMPLEMENTARY LAYERS",
    s34: "Payment execution and clearing evidence are different jobs.",
    s35: "HTTP-native payment requirements and execution around a request. A payment rail can settle the resulting obligation.",
    s36: "x402 documentation",
    s37: "Authorized budgets, verifiable metering and a net allocation with signed evidence. Complementary to payment rails, not a replacement.",
    s38: "Rail-agnostic is an architecture choice, not a list of completed integrations. Stripe has test evidence; production x402, bank and stablecoin adapters are not claimed here.",
    s39: "04 / DEVELOPER ENTRY",
    s40: "Keep the protocol inspectable.",
    s41: "Retained main-branch gateway examples below are illustrative requests, not live telemetry or a hosted public API.",
    s42: "Specification",
    s43: "Protocol documents",
    s44: "Public API hosting, distributed persistence, legal custody and production TEE/ZK verification remain outside this preview.",
    s45: "05 / DESIGN PARTNERS",
    s46: "Bring a concrete agent-service transaction.",
    s47: "For agent-platform and infrastructure founders: explore one capability, one budget policy and one verifiable settlement. Developers and diligence reviewers can inspect the evidence first.",
    s48: "Start a design-partner conversation",
    s49: "Opens a public GitHub issue. Share use case and rail requirements, not credentials, personal data or confidential customer information. No SLA or hosted availability is promised.",
    s50: "Open prototype. Test evidence, not production assurance.",
  },
  ZH = {
    scroll: "向下探索",
    example: "请求示例 / 非实时数据",
    verifyWord: "验证",
    netWord: "净额",
    s1: "流程",
    s2: "证据",
    s3: "开发者",
    s4: "开放协议 / 开发者预览",
    s5: "Agent 间支付的清算层。",
    s6: "预付保留积分、计量工作、净额结算、验证收据。不绑定支付轨道的证据层，而非另一个支付通道。",
    s7: "探讨设计伙伴合作",
    s8: "阅读协议规范",
    s9: "原型阶段。内部 escrow 是账本资金预留，不是法律托管；真实托管与合规须由持牌合作方承担。",
    s10: "01 / 清算流程",
    s11: "从授权执行，到可审计结算。",
    s12: "预付托管",
    s13: "通过 mandate 限定支出，将约定积分预留在内部 escrow。",
    s14: "哈希链计量",
    s15: "每条认可的计量记录关联前一条记录，篡改会破坏哈希链。",
    s16: "净额结算",
    s17: "按计量结果分配服务款与费用，按策略退回剩余积分。",
    s18: "签名与验证",
    s19: "无需运行账本，即可独立验证收据与计量链。",
    s20: "完整性不等于真实性：签名与 Merkle 证明认证记录，不证明服务质量。TEE/ZK 执行验证尚未实现。",
    s21: "02 / 验证证据 · 2026-10-22",
    s22: "已验证什么，尚未完成什么。",
    s23: "以下证据属于协议提交 54bd57f，尚未合入 main。测试模式不代表生产支付活动。",
    s24: "严格 escrow-v1 / 按需启用",
    s25: "状态机、独立验证器、签名授权与 Merkle 证明已落地；证据绑定的多签裁决仍依赖可信签名者。",
    s26: "查看带日期的证据",
    s27: "签名收据 / 测试模式",
    s28: "Stripe 入金 → 内部托管 → 计量 → 净额结算 → 签名收据，独立验证返回 VALID。不宣称真实客户或交易量。",
    s29: "查看带日期的证据",
    s30: "Transfer 已创建 / Payout 待完成",
    s31: "USD 0.50 换汇为 JPY 79 毛额 − JPY 6 手续费 = JPY 73 净额。测试 Transfer 已创建；Payout 因资金待可用而被拒。available_on：2026-10-29 08:00（UTC+8），不代表届时出金已完成。",
    s32: "查看带日期的证据",
    s33: "03 / 互补层次",
    s34: "支付执行与清算证据，是不同的职责。",
    s35: "围绕 HTTP 请求表达支付要求并执行支付，支付轨道可结算产生的应付款。",
    s36: "x402 文档",
    s37: "授权预算、可验证计量、附签名证据的净额分配。与支付轨道互补，而非替代它们。",
    s38: "轨道无关是架构选择，不等于各通道已经接通。Stripe 有测试证据；此处不宣称 x402、银行与稳定币生产适配器已完成。",
    s39: "04 / 开发者入口",
    s40: "让协议可供独立审查。",
    s41: "下方保留 main 分支的网关示例。这些是请求示意，不是实时活动或托管的公开 API。",
    s42: "规范",
    s43: "协议文档",
    s44: "公开 API 托管、分布式持久化、法律托管及生产 TEE/ZK 验证均不属于本预览的已完成能力。",
    s45: "05 / 设计伙伴",
    s46: "带来一个具体的 Agent 服务交易场景。",
    s47: "面向 Agent 平台与基础设施创始人：从一种能力、一套预算策略、一笔可验证结算开始。开发者与尽调方可先审查上方证据。",
    s48: "发起设计伙伴交流",
    s49: "将打开公开 GitHub Issue。请描述场景与通道要求，不要提交密钥、个人信息或客户机密。不承诺 SLA 或托管服务可用性。",
    s50: "开放原型。测试证据，不是生产保证。",
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
document.getElementById("epcode").addEventListener("focus", () => showExample(false));
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
  const capacity = 6000;
  const x = new Float32Array(capacity),
    y = new Float32Array(capacity);
  const vx = new Float32Array(capacity),
    vy = new Float32Array(capacity);
  const lane = new Float32Array(capacity),
    speed = new Float32Array(capacity);
  let w = 1,
    h = 1,
    count = 3600,
    raf = 0,
    last = 0,
    elapsed = 0;
  let px = -10000,
    py = -10000,
    parallax = 0,
    visible = true;
  let slowFrames = 0;
  function resize() {
    w = hero.clientWidth;
    h = hero.clientHeight;
    const dpr = Math.min(devicePixelRatio || 1, 1.75);
    canvas.width = Math.round(w * dpr);
    canvas.height = Math.round(h * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    count = w <= 768 ? 700 : Math.min(6000, Math.max(3000, Math.round(w * 3)));
    for (let i = 0; i < capacity; i++) {
      x[i] = Math.random() * w;
      lane[i] = (Math.random() - 0.5) * 2;
      speed[i] = 0.25 + Math.random() * 0.7;
      y[i] =
        h * 0.7 +
        Math.sin((x[i] / w) * 7 + lane[i] * 2) * h * 0.12 +
        lane[i] * h * 0.14;
      vx[i] = 0.5;
      vy[i] = 0;
    }
    ctx.fillStyle = "#101313";
    ctx.fillRect(0, 0, w, h);
    render(1, 0);
    schedule();
  }
  // Preallocated scalar/TypedArray simulation; no arrays, objects, closures or
  // color strings are constructed inside the particle/frame loop.
  function render(dt, t) {
    ctx.globalAlpha = 0.23;
    ctx.fillStyle = "#101313";
    ctx.fillRect(0, 0, w, h);
    ctx.globalAlpha = 1;
    const phase = t % 12;
    const pulse =
      phase > 8.8 ? Math.pow(Math.sin(((phase - 8.8) / 3.2) * Math.PI), 2) : 0;
    parallax += (((px < 0 ? 0.5 : px / w) - 0.5) * 12 - parallax) * 0.025 * dt;
    ctx.strokeStyle = "#99e5bb";
    ctx.lineWidth = 0.7;
    ctx.globalAlpha = 0.32 + pulse * 0.38;
    ctx.beginPath();
    for (let i = 0; i < count; i++) {
      const ox = x[i],
        oy = y[i];
      const base = h * 0.71 + Math.sin((ox / w) * 6.28 + t * 0.13) * h * 0.07;
      const spread =
        Math.sin((ox / w) * 8 + lane[i] * 3 + t * 0.09) * h * 0.1 +
        lane[i] * h * 0.17;
      const chain = Math.sin((ox / w) * 60) * h * 0.009;
      const target = base + spread * (1 - pulse) + chain * pulse + parallax;
      let ax = (0.55 + speed[i] + pulse * 2 - vx[i]) * 0.035;
      let ay = (target - oy) * (0.0015 + pulse * 0.009) - vy[i] * 0.045;
      const dx = ox - px,
        dy = oy - py,
        distance = dx * dx + dy * dy;
      if (distance < 19000 && distance > 1) {
        const force = (1 - distance / 19000) * 0.004;
        ax += dx * force;
        ay += dy * force;
      }
      vx[i] += ax * dt;
      vy[i] += ay * dt;
      x[i] += vx[i] * dt;
      y[i] += vy[i] * dt;
      if (x[i] > w + 10 || x[i] < -20 || y[i] < 0 || y[i] > h) {
        x[i] = 0;
        y[i] = target;
        vx[i] = 0.5;
        vy[i] = 0;
      } else {
        ctx.moveTo(ox, oy);
        ctx.lineTo(x[i] + 0.7, y[i]);
      }
    }
    ctx.stroke();
    ctx.globalAlpha = 1;
  }
  function frame(now) {
    raf = 0;
    if (document.hidden || !visible || motion.matches) {
      last = 0;
      return;
    }
    const ms = last ? Math.min(now - last, 40) : 8.33;
    last = now;
    elapsed += ms / 1000;
    if (ms > 23) slowFrames++;
    else slowFrames = Math.max(0, slowFrames - 1);
    if (slowFrames > 90) {
      count = Math.max(w <= 768 ? 400 : 3000, count - 500);
      slowFrames = 0;
    }
    render(ms / 16.667, elapsed);
    raf = requestAnimationFrame(frame);
  }
  function schedule() {
    if (raf) cancelAnimationFrame(raf);
    raf = 0;
    last = 0;
    if (!motion.matches && !document.hidden && visible)
      raf = requestAnimationFrame(frame);
  }
  hero.addEventListener(
    "pointermove",
    function (e) {
      if (e.pointerType === "touch") return;
      const box = hero.getBoundingClientRect();
      px = e.clientX - box.left;
      py = e.clientY - box.top;
    },
    { passive: true },
  );
  hero.addEventListener("pointerleave", function () {
    px = py = -10000;
  });
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
  if (!("IntersectionObserver" in window)) return;
  const steps = document.querySelectorAll(".ps");
  const sections = document.querySelectorAll(".sec:not(#loop) .wrap");
  const reveal = new IntersectionObserver(
    function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.remove("pending");
          reveal.unobserve(entry.target);
        }
      });
    },
    { threshold: 0.08 },
  );
  sections.forEach(function (el) {
    el.classList.add("reveal");
    if (!motion.matches && el.getBoundingClientRect().top > innerHeight)
      el.classList.add("pending");
    reveal.observe(el);
  });
  document.getElementById("loop").classList.add("chain-ready");
  // Distinct observer thresholds stagger the four segments on a shared desktop
  // row; mobile steps naturally cross the viewport one after another.
  steps.forEach(function (step, index) {
    const observer = new IntersectionObserver(
      function (entries) {
        if (entries[0].isIntersecting) {
          step.classList.add("active");
          observer.disconnect();
        }
      },
      { rootMargin: "0px 0px -" + (10 + index * 8) + "% 0px" },
    );
    observer.observe(step);
  });
})();

(function cursor() {
  const eligible = matchMedia("(pointer: fine) and (min-width: 769px)");
  const dot = document.createElement("div"),
    ring = document.createElement("div");
  dot.className = "cursor-dot";
  ring.className = "cursor-ring";
  dot.setAttribute("aria-hidden", "true");
  ring.setAttribute("aria-hidden", "true");
  document.body.append(dot, ring);
  let x = 0,
    y = 0,
    rx = 0,
    ry = 0,
    raf = 0,
    active = false;
  function tick() {
    rx += (x - rx) * 0.16;
    ry += (y - ry) * 0.16;
    ring.style.transform =
      "translate3d(" + (rx - 15) + "px," + (ry - 15) + "px,0)";
    if (Math.abs(x - rx) + Math.abs(y - ry) > 0.1 && active)
      raf = requestAnimationFrame(tick);
    else raf = 0;
  }
  function stop() {
    active = false;
    cancelAnimationFrame(raf);
    raf = 0;
    document.body.classList.remove("cursor-on", "cursor-over");
  }
  document.addEventListener(
    "pointermove",
    function (e) {
      if (!eligible.matches || motion.matches || e.pointerType === "touch") {
        stop();
        return;
      }
      x = e.clientX;
      y = e.clientY;
      if (!active) {
        rx = x;
        ry = y;
        active = true;
      }
      document.body.classList.add("cursor-on");
      document.body.classList.toggle(
        "cursor-over",
        !!e.target.closest("a,button,select"),
      );
      dot.style.transform =
        "translate3d(" + (x - 2) + "px," + (y - 2) + "px,0)";
      if (!raf) raf = requestAnimationFrame(tick);
    },
    { passive: true },
  );
  document.documentElement.addEventListener("pointerleave", stop);
  document.addEventListener("visibilitychange", function () {
    if (document.hidden) {
      stop();
      showExample(false);
    }
  });
  document.addEventListener("keydown", stop);
  eligible.addEventListener("change", stop);
  motion.addEventListener("change", function () {
    stop();
    showExample(false);
  });
})();
