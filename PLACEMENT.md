# NeuralClear 本次改动文件清单

这个文件夹里的所有文件,都按照**仓库内的原始路径结构**摆放。
推送时,把它们按相同路径覆盖进你的 neuralclear 仓库即可。

## 文件去哪里

```
你下载的文件                          →  覆盖到仓库的这个位置
─────────────────────────────────────────────────────────────
index.html                           →  仓库根目录/index.html   ← 网站
README.md                            →  仓库根目录/README.md

neuralclear/clearing.py              →  仓库/neuralclear/clearing.py
neuralclear/gateway.py               →  仓库/neuralclear/gateway.py
neuralclear/tenancy.py               →  仓库/neuralclear/tenancy.py   ← 新增
neuralclear/proofs.py                →  仓库/neuralclear/proofs.py    ← 新增
neuralclear/netting.py               →  仓库/neuralclear/netting.py   ← 新增
neuralclear/httpwire.py              →  仓库/neuralclear/httpwire.py  ← 新增
neuralclear/store.py                 →  仓库/neuralclear/store.py     ← 新增
neuralclear/buyer.py                 →  仓库/neuralclear/buyer.py     ← 新增
neuralclear/provider.py              →  仓库/neuralclear/provider.py  ← 新增
neuralclear/reputation.py            →  仓库/neuralclear/reputation.py← 新增

tests/test_*.py                      →  仓库/tests/   (6 个测试文件)
examples/closed_loop_demo.py         →  仓库/examples/ ← 新增
examples/commercial_demo.py          →  仓库/examples/ ← 新增
examples/integrations/mcp_bridge.py  →  仓库/examples/integrations/ ← 新增
```

## 最省事的覆盖方式(终端一条命令)

假设这个文件夹下载到了桌面,叫 `neuralclear-changes`,
而你的仓库在 `~/neuralclear`:

```bash
cp -R ~/Desktop/neuralclear-changes/. ~/neuralclear/
```

注意 `neuralclear-changes/.` 末尾那个 `/.` ——它表示"把文件夹里的内容
连同子目录结构一起复制进去",路径会自动对上,不会搞乱。
(这条命令也会复制本说明文件 PLACEMENT.md,推送前删掉它即可,
或者留着也无妨。)

## 覆盖后,推送前先验证

```bash
cd ~/neuralclear
python3 -m unittest discover
```

看到最后一行 `Ran 127 tests ... OK` 就说明一切正常,可以推送。

## 推送

```bash
git add -A
git commit -m "Add clearing engine, gateway, tenancy + security fixes"
git push origin main
```

网站(index.html)会随这次 push 一起更新,
Cloudflare Pages 检测到后约 30 秒内自动重新部署 neuralclear.org。
