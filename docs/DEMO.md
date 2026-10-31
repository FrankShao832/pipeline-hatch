# Pipeline Hatch — 90 秒演示脚本（v2.2.0）

> 用途：作品集 / 面试现场演一遍「一个 show 的环境是怎么被变成一条可 review 的记录的」。
> 全部动作都在 Settings 窗口里，**不碰一行启动器源码**。
> UI 文案是英文（工具面向英文流水线），脚本本身用中文写给你自己看。

## 开场前 30 秒准备

```bash
cd /Volumes/Development/tools/pipeline/pipeline_hatch
./env/bin/python -m launcher.main          # 真实模式：DB + 磁盘 + config/env.yaml
```

- 若 `config/env.yaml` 不存在，**这正好**——第一次保存会创建它，第 4 拍才有东西可 Revert。
- 想清场重演：把 `config/env.yaml` 与 `config/env.yaml.bak.*` 一起 trash。
- ⚠️ 第 6 拍会写真实 DB 行 + 真实目录。演示用 `/tmp/demo/projects/y_pipeline_projects` 这类**两层**路径 + 显眼名字（如 `DemoShow`），演完用右栏 Danger zone 的软删收掉（**磁盘文件不会被删**）。
- 根必须是 `<dev>/projects/<root-name>` 两层：平层 `/tmp/x` 推不出 `$DEV`，cache / assets / renders 三条会被**跳过**并给 `W_DEV`（2026-10-30 真机实测发现，按原来会去建 `/cache/x`）。

---

## 第 1 拍 · 一屏看全（0:00–0:10）

点主窗口 **Settings**。三栏，没有标签页：

```
Resolved Environment │ Preflight │ Project
```

**台词**：左边是「这次启动到底会注入什么」，中间是「有什么不对」，右边是「这个 show 自己拥有什么」。三栏是同一个上下文的三个面，所以不需要切页。

---

## 第 2 拍 · 换上下文，数字跟着换（0:10–0:25）

顶部上下文栏：`Project → DragonLand`、`Department → lighting`、`DCC → houdini`。

看左栏这三行变化：`SHOW`、`DEPARTMENT`、`CACHE_ROOT`（`.../cache/DragonLand`）。

**台词**：环境不是一堆全局变量，是**由上下文推导**出来的；同一个 show 换部门，`DEPARTMENT` 和缓存根就跟着走，没人手抄路径。

---

## 第 3 拍 · 双击改一个值（0:25–0:40）

左栏 `ASSET_ROOT` 的 **Value** 单元格双击 → 改成 `/tmp/assets-v2` → Enter。

- 页脚：`Saved just now`
- 该行 **Scope** 从 `[derived]` 变成 `[show]`，被覆盖的旧值留在 `shadowed` 里
- 磁盘上多出 `config/env.yaml` 与 `config/env.yaml.bak.<时间戳>`

**台词**：改值不是改代码。它落进一个**可 diff、可 review 的文件**，而且只写 `show` 层——不需要问用户"这条属于哪一层"，因为上下文栏已经指明了唯一一个项目。

---

## 第 4 拍 · 一键撤回（0:40–0:50）

页脚 **Revert**（第 3 拍之后才亮）。

- 值回到推导值，Scope 回到 `[derived]`
- 页脚：`Saved reverted · previous overrides restored`
- 备份**不消耗**，误点两次也安全

**台词**：即时生效的系统必须配一个同样即时的撤销。备份是每次写入前自动留的，所以撤销不需要 "OK / Cancel" 事务，也不需要用户记住旧值。

---

## 第 5 拍 · 建一个 show，先看它要干什么（0:50–1:05）

右栏 **Project** 标题右侧 `+` → 对话框：

- Name：`DemoShow`（Work root / Publish root 已经预填成现有 show 用的卷）
- 实时读数：**`Will create 5 folders · will write 2 overrides`**（绿色）

打一个非法名（如 `1Bad`）→ `Create` 立刻变灰，底下写明 `Invalid project name`。

**台词**：这行数字不是界面自己算的，是真调用 `create_project(dry_run=True)` 的返回值——**预览和结果必须是同一次计算**，否则预览只是装饰。

---

## 第 6 拍 · Create，上下文自动跳到新 show（1:05–1:20）

点 **Create**。窗口整体切到 `DemoShow`：

- 右栏 **HEALTH**：`Ready`，`folders 5/5`
- 右栏 **ENVIRONMENT**：`show 2`，并列出基线两条
- 左栏出现 `OCIO = ${DEV}/color/aces_cg.ocio`（`[show]`）与 `FPS = 24`（`[show]`）

**台词**：建项目 = 四件事一次做完（DB 行、工作树、发布根、**基线环境**）。基线只写"算不出来的那两条"（色彩配置、帧率）；`CACHE_ROOT/ASSET_ROOT/RENDER_ROOT` 是推导值，**故意不写**——写进去就是第二份真相，日后会静默压过推导。

---

## 第 7 拍 · 把检查结果带走（1:20–1:30）

中间 **Preflight**：`W_WHITELIST`（这个键不在 `dcc.yaml: pipeline.env_vars`，DCC 层会丢掉）、`W_GUARDED`（`OCIO` 跨部门必须一致）之类的实话。

底部 **Copy .env** → 粘到终端 / 交给 DCC。

**台词**：最后一步是"可复现"：同一份解析结果既能贴进 shell，也能被 DCC 读到；左边是答案，中间是它为什么可能不生效，右边是这个 show 的证据。

---

## 收尾

```bash
# 看这次演示在磁盘上留下了什么
ls -l config/env.yaml*
cat config/env.yaml
```

清理：右栏 `Danger zone` → 停用项目（软删，`enabled=False`，目录保留）；`config/env.yaml` 里删掉对应 `scopes.show.DemoShow`。

---

## 每一拍对应的能力（面试可直接念）

| 拍 | 能力 | JD 关键词 |
|:--|:--|:--|
| 1 | 三个视图吃同一个上下文模型 | data flow |
| 2 | 环境由上下文推导，非硬编码 | reproducibility |
| 3 | 覆盖是文件（可 diff / review），只写一层 | review, version control |
| 4 | 即时生效 + 一键撤销（写前留备份） | safe iteration |
| 5 | dry-run 预览 = 真调用 | idempotent creation |
| 6 | 建项目一次完成四处写入，基线只写不可推导项 | avoiding duplicated truth |
| 7 | 诊断分级 + 结果可导出 | debuggability, publishing |
