# broom 🧹

> Claude Code 里的代码质量标尺，也是重构时的工具。

broom 是给 Coding Agent 用的工具，自己不带任何模型。它让 Claude 的改动在离开会话之前，先过一遍项目自己的格式化工具、lint 工具和类型检查；有人问起代码状况时，它用同一种量法量整个仓库。检查一次改动时，它评判这次改动和它碰到的代码，所以老仓库里的旧警告不会压到一个小修复上。类型错误是唯一的例外，因为改了签名会弄坏任何地方的调用方。

[English](../README.md)

---

## 它做什么

- 🧰 **配置**：在仓库里开会话时，broom 发现缺什么，Claude 就提议帮你安装和配置。
- 🧹 **清扫**：每次编辑后，它格式化文件，并把快速 lint 发现的问题告诉 Claude。提交时和每轮对话结束时，它对 Claude 的改动做格式化、lint 和类型检查，问题解决前不放行。
- 🧪 **测过才算完**：改了代码的一轮对话，要等项目的测试在这些代码上跑过才能结束，否则要留下你看得到的理由。
- 👃 **闻味道**：改动让代码过长、嵌套过深或出现重复时会被拦住，直到清理干净，或带理由放行。
- 👀 **看见**：六种语言的语言服务器让 Claude 边改边看到诊断。
- 📊 **诊断**：`broom diagnose`、`broom stats` 和 `broom compare` 给出整个仓库在重构前后的数字。
- 🩺 **体检**：会话开始时它数一遍仓库里的腐化，某个数字变大了就告诉 Claude 一次。

没有你的同意，什么都不装。被拦下的问题要么修好，要么带着记录在案的理由放行。

---

## 安装

```text
/plugin marketplace add jinhuang712/claude-code-broom
/plugin install broom@claude-code-broom
```

需要 macOS、Claude Code 2.1.271 或更高版本、Python 3.9+（命令名 `python3`）和 git。Linux 没有测试过，Windows 不支持。其余内容在 [INSTALL.md](INSTALL.md)（英文）：终端里的装法、每种语言的工具、更新和卸载。

---

## 怎么用

在某个仓库里开一个会话。缺工具或缺配置时，Claude 会提议运行 `/broom:setup`，它最多问两个问题。

然后让 Claude 干活。它提交的改动违反规则时，提交会被拦下，并附上一份报告：

```text
[broom] Commit blocked: 2 issue(s) in the files being committed. Fix them and commit again.

oxlint (~/code/app):
  src/api/client.ts:42:5  typescript(no-floating-promises)  Promises must be awaited
tsc (~/code/app):
  src/pages/home.tsx:17:9  TS2345  Argument of type 'string' is not assignable to 'number'  [not in the changed files]

Trying again passes nothing: only a fix does, or accepting with a reason. If one predates this change or is a false positive, run `broom known --accept "<why>"`, then commit again.
```

Claude 修好问题后再次提交。broom 有三个命令，上面这些都不需要你运行它们：

| 命令 | 做什么 |
|---|---|
| `/broom:setup` | 先问你，再安装缺少的工具、添加配置 |
| `/broom:status` | 说明哪些检查在运行，以及 broom 最近拦了、修了、放行了什么 |
| `/broom:scan` | 在一个范围内运行工具，列出发现的问题，不做任何修改 |

扫描的范围用你自己的话说：

```text
/broom:scan
/broom:scan src/api
/broom:scan 最近 3 个提交
```

想修掉发现的问题，说出要修哪些即可。Claude 会从最严重的开始，小步、带测试地清理。

---

## 配置

`/config` 里的四个设置都从默认值开始，从不询问。仓库根目录的 `.broom.json` 可以为单个仓库覆盖它们，还能排除路径、调整坏味道的上限。[F7: Settings](features/F7-settings.md)（英文）列出了全部设置。

---

## 架构

Claude Code 在会话开始、收到提示、调用 Bash、Bash 命令失败、编辑文件和一轮对话结束时启动 broom 的某个钩子。钩子对改动的部分运行项目自己的工具，然后以拦截、一条说明或什么都不说退出。

```
Claude Code
  │ SessionStart · UserPromptSubmit · PreToolUse(Bash) · PostToolUse(edit) · PostToolUseFailure(Bash) · Stop · SubagentStop
  ▼
hooks/hooks.json ──▶ hooks/commit.sh ──▶ bin/broom ──▶ lib/broom/
                                            ▲              │
git pre-commit hook ────────────────────────┘              ├──▶ the project's tools (formatters, linters, type checkers)
skills/ (setup · status · scan · clean) ───▶ bin/broom    ├──▶ defaults/ (configs where a project has none)
.lsp.json ──▶ language servers                             └──▶ the data directory (state shared by every hook)
```

---

## 文档（英文）

- [PROPOSAL.md](PROPOSAL.md) 说明 broom 为什么存在。
- [PHILOSOPHY.md](PHILOSOPHY.md) 记录它的立场。
- [DESIGNS.md](DESIGNS.md) 记录每个设计都必须满足的承诺。
- [FEATURES.md](FEATURES.md) 列出它做什么。
- [CLI.md](CLI.md) 描述 `broom` 命令。
- [INSTALL.md](INSTALL.md) 讲安装、更新和卸载。
- [GLOSSARY.md](GLOSSARY.md) 固定术语。
- [ARCHITECTURE.md](specs/ARCHITECTURE.md) 画出各个部分。
- [GOALS.md](plan/GOALS.md) 记录检查什么。
- [ROADMAP.md](plan/ROADMAP.md) 说明接下来做什么。
- [ISSUES.md](plan/ISSUES.md) 和 [TODO.md](plan/TODO.md) 记录未完成的工作和未回答的问题。
- [CONTRIBUTING.md](CONTRIBUTING.md) 说明怎么修改 broom。
- [AGENTS.md](../AGENTS.md) 记录在这个项目上工作的 agent 要守的规则。
- [CHANGELOG.md](../CHANGELOG.md) 列出每个版本。

---

## 许可证

[MIT](../LICENSE)
