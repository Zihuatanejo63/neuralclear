# NeuralClear Discord Community Setup

## 创建 Discord 服务器

### Step 1: 创建服务器
1. 打开 Discord: https://discord.com/
2. 点击左侧 "+" 号 → "创建我的"
3. 选择"仅供我和我的朋友使用"
4. 服务器名称: `NeuralClear - AI Agent Protocol`

### Step 2: 设置频道结构

```
neuralclear/
├── #welcome              # 欢迎频道
├── #announcements        # 公告频道
├──
├── 📢 announcements/     # 公告分类
│   ├── releases         # 版本发布
│   └── events           # 活动公告
│
├── 💬 general/           # 讨论分类
│   ├── intro            # 自我介绍
│   ├── general          # 通用讨论
│   └── show-and-tell    # 展示项目
│
├── 🔧 development/      # 开发分类
│   ├── python-sdk       # Python 开发
│   ├── rust-sdk         # Rust 开发
│   ├── integrations     # 框架集成
│   └── help             # 技术帮助
│
├── 🧪 protocol/         # 协议分类
│   ├── specs            # 协议规范讨论
│   ├── research         # 研究与设计
│   └── feedback         # 反馈建议
│
└── 🎉 community/        # 社区分类
    ├── events           # 社区活动
    ├── off-topic        # 闲聊
    └── memes            # 表情包
```

### Step 3: 设置机器人

添加 NeuralClear Bot:

1. 前往 Discord Developer Portal: https://discord.com/developers/applications
2. 创建新应用: "NeuralClear Bot"
3. 设置 bot 头像和名称
4. 启用 SERVER MEMBERS INTENT
5. 生成 bot token
6. 邀请链接格式:
```
https://discord.com/api/oauth2/authorize?client_id=YOUR_CLIENT_ID&permissions=8&scope=bot%20applications.commands
```

### Step 4: 邀请链接

创建永久邀请:
```
https://discord.gg/neuralclear
```

(需要先创建服务器才能生成链接)

---

## 社区运营计划

### 第一周：启动
- [ ] 创建 Discord 服务器
- [ ] 设置频道和权限
- [ ] 添加 bot (MEE6 或 Carl-bot)
- [ ] 邀请早期开发者

### 第二周：增长
- [ ] 发布公告到 Reddit/Hacker News
- [ ] 推特宣传
- [ ] 发布首次社区更新

### 第三周：活动
- [ ] 宣布 Hackathon
- [ ] 创建贡献指南
- [ ] 设立奖励机制

### 第四周：发布
- [ ] v0.2 版本发布
- [ ] 媒体宣传
- [ ] 合作伙伴公告

---

## 快速创建脚本

如果想用命令行创建基本结构，可以用 Discord API 或第三方工具。但最简单的是手动在 Discord UI 中创建。

---

## 替代方案：使用 GitHub Discussions

如果不想自己托管 Discord，可以用 GitHub 自带的 Discussions:

1. 进入 https://github.com/Zihuatanejo63/neuralclear
2. Settings → Features → Discussions → Enable
3. 设置讨论分类

**优点:** 无需管理，集成在 repo 中
**缺点:** 功能比 Discord 少

---

## 选择你想用的方案：

1. **Discord** - 需要你手动创建，我可以帮你设置 bot
2. **GitHub Discussions** - 我可以直接帮你启用
3. **两者都要** - 最佳方案

告诉我你选哪个？
