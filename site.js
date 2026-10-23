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
    engine: "CLEARING ENGINE FOR AGENT SERVICES",
    rail: "RAIL-AGNOSTIC · EST. 2026",
    sequence: "ESCROW — METER — NET — SETTLE",
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
    engine: "面向 AGENT 服务的清算引擎",
    rail: "轨道无关 · 始于 2026",
    sequence: "托管 — 计量 — 净额 — 结算",
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
      "translate3d(" + (rx - 18) + "px," + (ry - 18) + "px,0)";
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
