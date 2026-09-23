# broom 🧹

**给 Claude Code 的自动代码清洁插件。** broom 为仓库配好需要的格式化工具、lint 工具、类型检查和语言服务器，然后在
该清扫的时候把 Claude 的改动清扫一遍：按项目自己的规则，格式整齐、没有 lint 问题、类型正确。

[English](../README.md)

## 它做什么

- **配置**：在仓库里开会话时发现缺什么，让 Claude 提议帮你安装和配置。没有你的同意，什么都不装。
- **清扫**：该清扫的时候，broom 对 Claude 的改动做格式化、lint 和类型检查，问题解决前不放行。
- **看见**：为 Go、TS/JS、Rust、Python、CSS（含 SCSS、Less）提供语言服务器，Claude 边改边看到诊断。

它用你项目自己的工具和配置，只看改动的部分，同样的结果不会拦第二次。

```text
[broom] Commit blocked: 2 issue(s) in the files being committed. Fix them and commit again. If one is
pre-existing or a false positive, say so and run the same commit again: broom lets an unchanged result through.

oxlint (~/code/app):
  src/api/client.ts:42:5  typescript(no-floating-promises)  Promises must be awaited
tsc (~/code/app):
  src/pages/home.tsx:17:9  TS2345  Argument of type 'string' is not assignable to 'number'  [not in the changed files]
```

## 安装

**需要：** Claude Code 2.1.271 或更高版本、Python 3.9+（命令名 `python3`，macOS 自带的即可）、git。

1. 在 Claude Code 里添加 marketplace 并安装插件：

   ```text
   /plugin marketplace add jinhuang712/claude-code-broom
   /plugin install broom@claude-code-broom
   ```

   或者在终端里：

   ```bash
   claude plugin marketplace add jinhuang712/claude-code-broom
   claude plugin install broom@claude-code-broom
   ```

2. 在某个仓库里开一个会话。缺东西时 Claude 会提议运行 `/broom:setup`，接受即可，也可以自己运行。它最多问四个问题，
   安装你选的工具，再检查一遍结果。

3. 可选：在 `/config` 里调整设置。

想自己装工具的话，broom 用的是这些：

| 语言 | 安装 |
|---|---|
| Go | `brew install golangci-lint` · `go install golang.org/x/tools/gopls@latest` |
| TS/JS | 在项目里 `npm i -D oxlint oxlint-tsgolint oxfmt` · `npm i -g typescript-language-server`（语言服务器） |
| Rust | `rustup component add clippy rustfmt rust-analyzer` |
| Python | `brew install ruff` · `npm i -g pyright` |
| CSS、SCSS、Less | 在项目里 `npm i -D stylelint`，有 SCSS 再加 `stylelint-config-recommended-scss`，有 Less 再加 `stylelint-config-recommended-less` · `npm i -g vscode-langservers-extracted` |

不要同时启用 `gopls-lsp`、`typescript-lsp`、`rust-analyzer-lsp` 或 `pyright-lsp`：两个插件服务同一类文件时，
只有一个语言服务器会启动。出现这种情况 `broom doctor` 会告诉你。

**更新：** `claude plugin marketplace update claude-code-broom && claude plugin update broom@claude-code-broom`
**卸载：** `claude plugin uninstall broom@claude-code-broom`

## 使用

大多数时候不用管：broom 会自己清扫。想先看看的话，用自己的话让它清扫：

```text
/broom:sweep
/broom:sweep 我暂存的改动
/broom:sweep 最近 3 个提交
/broom:sweep 整个仓库
```

| 设置 | 默认 | 可选 |
|---|---|---|
| `format_on` | `commit` | `edit`（每次编辑后也格式化）、`off` |
| `check_on` | `commit` | `stop`（每轮对话结束时也检查）、`off` |
| `format_scope` | `changed` | `function`（整个改动过的函数；CSS 里是整条规则）、`file` |

仓库根目录的 `.broom.json` 可以为单个仓库覆盖这些设置，还能排除路径：

```json
{ "format_scope": "function", "exclude": ["vendor/**", "**/*.pb.go"] }
```

`broom` 命令也在 PATH 上：`broom sweep`、`broom doctor`、`broom known`。详见 [Features](FEATURES.md)。

## 文档（英文）

[Philosophy](PHILOSOPHY.md) · [Goals](GOALS.md) · [Proposal](PROPOSAL.md) · [Design](DESIGN.md) ·
[Features](FEATURES.md) · [Changelog](../CHANGELOG.md)

## 许可证

[MIT](../LICENSE)
