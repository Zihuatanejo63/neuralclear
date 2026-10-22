# 真实 Stripe 测试模式运行结果：2026-10-22

## 结论

**部分完成，不是完整 payout 闭环。**

通过真实 Stripe API 创建并确认一笔 USD 0.50 测试付款；完成 escrow 入账、
签名 mandate 校验、hash 链计量、内部净结算、Ed25519 收据签名与独立验证。
没有创建 transfer 或 payout：账户没有 Connect 服务方收款账户，且
`payouts_enabled=false`、可用余额为 0。未伪造任何外部对象或成功状态。

执行开始：2026-10-22 13:27:50（Asia/Shanghai；UTC 05:27:50）。
运行入口：`examples/escrow_channel_live_test.py`。
真实 HTTP 经 `neuralclear.stripe_channel.StripeHTTP` 的 urllib 传输；无 fake opener。
密钥只从用户配置文件读取，没有写入源码、输出或本报告。
所有支付对象均返回 `livemode=false`；test mode 不产生真实资金划拨。

## 对象 ID 清单

以下对象均来自本次真实 API 响应，并经过读取核对：

| 对象 | ID | 结果 |
| --- | --- | --- |
| 平台账户 | `acct_1TQJQcE5PKlMxr4M` | API 读取成功 |
| PaymentIntent | `pi_3UTEXcE5PKlMxr4M1BLslkNm` | `succeeded`，USD 50 cents，amount_received=50 |
| Charge | `ch_3UTEXcE5PKlMxr4M1o0whdoo` | `succeeded`，paid=true，captured=true |
| Balance transaction | `txn_3UTEXcE5PKlMxr4M15dVkqrq` | JPY 净额 73，`pending` |
| Connect 服务方账户 | 未找到 | GET accounts 返回空列表，has_more=false |
| Transfer | 未创建 | 没有合法 destination，未提交 POST transfers |
| Payout | 未创建 | 未提交 POST payouts，无 po_ ID |

可在该 Stripe 账户的相同测试环境 Dashboard 中按上述真实 ID 查找。
内部交易 ID（不是 Stripe 对象）：
`nc_stripe_test_aafa336c0da8416a9bcc34c96cae4abe`。

## 每一步结果

| 步骤 | 结果 | 证据 / 边界 |
| --- | --- | --- |
| 账户预检 | 完成 | charges_enabled=false、payouts_enabled=false、default_currency=jpy |
| Mandate | 完成 | Ed25519 签名；单笔、每日、总预算均为 50 cents；绑定 buyer/research/summarize |
| 创建 PaymentIntent | 完成 | 状态先为 requires_payment_method；金额为最低 USD 50 cents |
| 确认付款 | 完成 | 使用 Stripe `pm_card_visa`（4242 测试场景），返回 succeeded |
| Escrow 托管记账 | 完成 | 重新 GET PaymentIntent 校验实际状态、金额、币种和 metadata 后入账 |
| 重复确认 | 完成 | 再确认一次，held 与 total_supply 仍为 50，没有重复入金 |
| 执行授权与计量 | 完成 | 执行前检查签名、有效期、撤销及预算；生成 1 条 hash 链记录 |
| 内部净结算 | 完成 | provider=50、buyer=0、fee_pool=0、held=0、total_supply=50 |
| 外部 payout | 前置条件阻塞 | 未找到服务方 connected account，不能用平台账户冒充服务方 |
| 签名收据 | 完成 | Ed25519；所有密钥现场随机生成，私钥不在仓库内 |
| 独立验证 | 完成 | 子进程仅输入收据、计量链和公钥；返回 VALID，退出码 0 |

本次协议服务费设为 0，入金和内部服务结算均为 50 cents，避免额外增加测试金额。
内部服务执行仍是协议演示结果，不是实际调用第三方收费模型。

## Stripe 原始状态与卡点

本次所有已提交请求均成功，**没有 Stripe 4xx/5xx 原始报错可记录**。
不能将下面的前置条件检查伪装成 Stripe 拒绝了一个实际 payout 请求：

```json
{
  "charges_enabled": false,
  "payouts_enabled": false,
  "default_currency": "jpy",
  "disabled_reason": null,
  "connected_accounts": [],
  "accounts_has_more": false
}
```

尽管账户状态显示 charges_enabled=false，实际测试 PaymentIntent 确认确实成功；
报告以 API 返回的真实支付对象为准，不将账户标志推断成测试收款失败。

Charge 的实际 Stripe 入账结果：

```json
{
  "amount": 79,
  "currency": "jpy",
  "fee": 6,
  "net": 73,
  "status": "pending",
  "available_on": 1793232000
}
```

运行后的平台余额：available JPY 0，pending JPY 73。
**内部 USD 50 cents 的应付余额不等于可立即提款的 Stripe USD 余额。**
Stripe 已做币种转换并扣费；本轮没有改写核心账本来伪装这部分外部汇率、手续费
和可用余额。收据证明内部清算守恒，不证明平台偿付能力、银行付款或汇率对账完成。

继续 payout 前需要用户选择/配置合法的测试 Connect 服务方账户及其 payout 条件，
解决币种和可用余额问题。脚本不自动注册账户、不补充值、不提高交易金额，也不
转入 live mode。已有交易应按日志进行明确的外部对账，不要换目录盲目重跑入金。

## 可复核证据

公开、无密钥的验证材料位于：
`docs/p0-live-stripe-evidence-2026-10-22.json`，包含完整 receipt、meter chain 和公钥。
其中没有 Stripe secret 或签名私钥。Stripe 对象与内部交易的对应关系来自 API
metadata 和运行日志，不是声称 Stripe 自身签署了 NeuralClear 收据。

本机完整运行目录（权限 700，包含签名私钥，不可提交）：
`/private/tmp/neuralclear-stripe-live-20261022`。
内有追加式账本、checkpoint、脱敏 evidence.json、收据和链；临时目录可能被系统清理。
该本地 checkpoint 只是演示锚点，不代表生产环境的独立防回滚存储。

实际独立验证命令：

```sh
python3 -m neuralclear.verify \
  /private/tmp/neuralclear-stripe-live-20261022/receipt.json \
  /private/tmp/neuralclear-stripe-live-20261022/chain.json \
  --algorithm Ed25519 --key-id clearing \
  --key-file /private/tmp/neuralclear-stripe-live-20261022/public.key
```

输出：`VALID`。运行器因 payout 未完成而返回退出码 **2**，不是成功码 0。

## 测试和变更边界

新增运行器与离线安全回归测试；测试覆盖拒绝 live 密钥/对象、脱敏 Stripe 原始错误、
禁止跨站重定向、成功响应不泄露 client_secret，以及拒绝复用运行目录。
全量 pytest 无 Stripe 网络调用。核心包、旧 API、已有网站和文档未改动。
未 git commit，未 push。

最终验证：Python 3.13.1 下 `/tmp/neuralclear-stripe-tests/bin/python -m pytest tests/`
返回 **130 passed**，包括本轮 7 个新测试。独立验证 CLI 再次返回 VALID。
`git diff --check` 通过；源码、测试、公开结果和脱敏运行日志的实际密钥字节扫描通过，
检查过程未输出密钥内容。

官方参考：
[测试 PaymentMethod](https://docs.stripe.com/testing)、
[确认 PaymentIntent](https://docs.stripe.com/api/payment_intents/confirm)、
[Transfer](https://docs.stripe.com/api/transfers/create)、
[Payout](https://docs.stripe.com/api/payouts/create)。
