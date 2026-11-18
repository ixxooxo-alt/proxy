# r22 进行中的存档（2026-11-18）

额度用完、会话中断以后先提交的检查点，不是送审稿。`main` 没动。

## 已经做完、在这个提交里的

- PR #10（全项目复核，`docs/evidence/review-r21b-full/`）F01–F10 的代码改动：转换器（只能走 TLS 的协议总是开 TLS 并在报告里提示、布尔字段严格、packet → packetaddr）、
  写盘前检查、Copilot 的 7 个主机、私密目录未刷新文件的登记（`not_refreshed`）、暂存文件先登记、`.gitignore`、打包只从提交取文件、验包看真实退出码且不删本轮以外的目录、
  `selftest_package.py`、`r21_private_vs_r20.py` 的绝对路径、`r22_private_vs_r21b.py`；变异“发现”的口径收紧、M182 的预设、M211–M224。
- 版本：统一源 2026.11.18-1、生成器 1.13.0；`dist/`、`docs/04`、上游对照记录、官方内核快照（`tests/data/real_sets.json`）都已重新生成。
- 356 项测试通过（Python 3.13）；M14、M182、M211–M224 试跑都被发现（`handoff/notes/r22_draft/logs/mutations-trial-*.log`）；
  打包验包自测 24 项都符合；r22 相对 r21b 的私密产物只差有意改的地方；sing-box 取值逐个核对（`singbox-enum-sweep.log`）。
- 另两份贴来的审核原文已存档：`docs/evidence/review-r21b-full-2/`、`review-r21b-full-3/`；使用者原话记在 `docs/00` 最后一节。

## 还没做的

1. 应用 `enum_patch.py`（F03 的同一类：sing-box 不认的加密方式、flow、拥塞控制、uTLS 指纹、多路复用协议跳过节点；`client-fingerprint: none` 不写 uTLS；Reality 没有指纹跳过），
   配测试、样例节点“台湾 VMess 指纹 none”、变异 M225–M228。
2. 第二份审核（C1–C9、S1–S2）和第三份审核（F01–F06、建议 1–3）逐条核实、改属实的、同一类自查；Claude 的 17 个域名。
3. 文档：`docs/08` 第 21–23 轮（第 21 轮草稿在本目录）、`docs/06`、`docs/07`、`docs/05` 送审稿说明、两份 README、`00-审核说明.md`、`PROJECT_STATE.md`、`handoff/README.md`、
   `handoff/release/README.md`（先提交再打包再验包）、`CLAUDE.md` 的变异类数。
4. 快速检查（`handoff/notes/r22_draft/run_quick.sh`）、提交、推送，送审稿交给使用者。
