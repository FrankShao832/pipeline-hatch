# Pipeline Hatch — 录屏分镜本（求职投递用，v2.2.0）

> 目标：**3 分钟屏录**，让看的人相信三件事——① 一个 show 的环境是一条可 diff 的记录；② 这条记录真的把 DCC 带起来了；③ 换台机器同一份文件还是对的。
> 观众：Pipeline TD / Houdini TD 的技术面。他们不看 UI 多漂亮，看数据流、可复现、以及"你是不是真的跑过"。
> UI 文案是英文（工具面向英文流水线），台词是中文——你可以照着念，也可以只用字幕。

---

## 录前检查清单（5 分钟）

```bash
cd /Volumes/Development/tools/pipeline/pipeline_hatch

# 1) 从这里开始才干净：上一轮演示留下的覆盖全部清掉
trash config/env.yaml config/env.yaml.bak.* 2>/dev/null

# 2) 基线必须是绿的（片头字幕报的就是这个数字）
QT_QPA_PLATFORM=offscreen ./env/bin/python -m pytest -q | tail -2

# 3) 确认两个 DCC 能被探针叫起来（片子里的"回执"就是它打印的）
./env/bin/python tools/verify_launch_env.py --dcc maya    --project CyberPunk -d fx | tail -6
./env/bin/python tools/verify_launch_env.py --dcc houdini --project CyberPunk -d fx | tail -6
```

- ⚠️ **中栏 Preflight 现在开场就是 8 条 `W_PATH` / `W_PUBLISH`**，全部来自 `demo01` / `test_01`–`test04` 这些半成品测试项目（磁盘缺目录）。片子开拍前二选一：**禁用/清掉这些项目行**，或接受它并在台词里主动解释一句（"这是我自己的垃圾测试项目"其实也不难看，但会占掉中栏第一屏）。
- 终端字号调到 16pt 以上、深色主题；关掉无关窗口与通知。
- 第 3 拍会写真实文件、第 6 拍会写真实 DB 行——演示名用 `DemoShow`，收尾软删。

---

## 分镜

### 0:00–0:12 · 钩子（字幕 + 主窗口）

**画面**：主窗口，左栏项目树 CyberPunk → seq001_city → cy_city_0010，右栏部门与 DCC 下拉。
字幕：`One show. One environment. A file you can diff.`

**台词**：这是我们的 DCC 启动器。今天只讲一件事：一个 show 的环境是怎么被变成一条可 review 的记录的。

---

### 0:12–0:30 · 第 1 拍 一屏看全

**动作**：点 **Settings**。三栏出现。

**台词**：左栏是「这次启动到底会注入什么」，中间是「有什么不对」，右边是「这个 show 自己拥有什么」。三栏是同一个上下文的三个面，所以不需要切页。

---

### 0:30–0:50 · 第 2 拍 换上下文，数字跟着换

**动作**：上下文栏 `Project → DragonLand`、`Department → lighting`、`DCC → houdini`。

**台词（指左栏）**：`SHOW`、`DEPARTMENT`、`CACHE_ROOT` 一起变了。环境不是一堆全局变量，是**由上下文推导**出来的——同一个 show 换部门，缓存根就跟着走，没人手抄路径。

---

### 0:50–1:10 · 第 3 拍 双击改一个值（核心）

**动作**：左栏 `OCIO` 的 Value 双击 → 输入 `${DEV}/color/aces_cg.ocio` → Enter。

- 页脚 `Saved just now`
- 该行 Scope 从 `[derived]` 变成 `[show]`
- 中栏多一条 `W_GUARDED`（"色彩管理跨部门必须一致"）——**这条要主动念出来**，它是设计不是 bug

**台词**：改值不是改代码。它落进一个可 diff、可 review 的文件，而且只写 `show` 层——上下文栏已经指明唯一一个项目，不需要再问用户"这条属于哪一层"。

---

### 1:10–1:25 · 第 4 拍 Revert（信任感）

**动作**：点页脚 **Revert**。`OCIO` 回到 `[derived]`，页脚 `Saved reverted · previous overrides restored`。

**台词**：即时生效必须配即时撤销。备份是每次写入前自动留的，所以撤销不需要 OK/Cancel，也不需要用户记住旧值。备份不消耗，点两次也安全。

---

### 1:25–1:50 · 第 5 拍 终端证据（A）

**动作**：切到终端，逐行敲：

```bash
cat config/env.yaml                 # ← 刚才那一笔，文件里长这样
ls -l config/env.yaml.bak.*         # ← 每次写入都留了一份
./env/bin/python tools/print_env.py --project CyberPunk -d fx --dcc houdini
./env/bin/python tools/print_env.py --project CyberPunk -d fx --dcc houdini --export
QT_QPA_PLATFORM=offscreen ./env/bin/python -m pytest -q | tail -2
```

**屏幕要点**：`[show:CyberPunk]` 的来源标记、`20 variables · 2 overridden`、最后一行 **`338 passed`**。
**字幕**：`the same resolve, from a shell · 338 tests`

**台词**：面板里看到的东西，终端里一模一样——因为它调的不是另一套逻辑。这个脚本农场和 CI 也能用。

---

### 1:50–2:20 · 第 6 拍 真的进 DCC（B，高潮）

**动作**：

```bash
./env/bin/python tools/verify_launch_env.py --dcc houdini --project CyberPunk -d fx
```

**屏幕要点**：`overrides 2: FPS[show], OCIO[show]` → 然后 `what houdini sees (3.11.7)` 下面 `OCIO=/Volumes/.../aces_cg.ocio`。

再跑一遍 Maya（`--dcc maya`）证明不是单点。

**台词**：这不是"预览说会注入"，是启动器真的把 env 交给 DCC 的进程，然后我们在 **hython / mayapy 里面把 `os.environ` 打出来**。同一条链路刚才已经在设置面板里点过了。

---

### 2:20–2:45 · 第 7 拍 建一个 show（收口）

**动作**：右栏标题 `+` → `DemoShow` → 绿字 `Will create 5 folders · will write 2 overrides` → **Create** → 窗口整体切到新 show，HEALTH `Ready`，ENVIRONMENT `show 2`，左栏出现 `OCIO` / `FPS`（`[show]`）。

**台词**：建项目一次做完四件事：DB 行、工作树、发布根、基线环境。基线只写"算不出来的那两条"——色彩配置和帧率；`CACHE_ROOT` 这类推导值故意不写，写进去就是第二份真相。

---

### 2:45–3:00 · 收尾

**画面**：回到启动器主窗口，点 **Launch**，Houdini 起来（可以只拍启动瞬间）；叠字卡。

字幕：

```
Pipeline Hatch v2.2.0 · 338 tests
config/env.yaml — four scopes, atomic writes, one-click revert
launcher → publisher → asset manager → stage weaver: one pipeline, four tools
```

---

## 台词里可以主动交代的三个"我知道它的边界"

面试官信的是这个，不是完播率：

1. **`W_GUARDED` 是真的警告，不是装饰**——`OCIO` 在 show 层覆盖会让两个部门看到不同色彩，这条会被中栏点名。
2. **白名单是配置，不是魔法**——`OCIO` / `FPS` 原来不在 `dcc.yaml: pipeline.env_vars` 里，会被 DCC 层丢掉；今天把它们加进白名单，是因为"设了却悄悄不生效"比不做更坏。
3. **resolver 还没有 seq/shot 层**，镜头粒度只在显示上；`delete_env_row` 还是空的。

---

## 附：一拍一张的证据

| 拍 | 一条命令 / 一个动作 | 证明什么 |
|:--|:--|:--|
| 3 | 双击 `OCIO` → `cat config/env.yaml` | 覆盖是一条可读记录 |
| 4 | `Revert` → `ls config/env.yaml.bak.*` | 撤销靠备份，不靠事务 |
| 5 | `print_env.py` / `--export` / `pytest -q` | 面板与终端同一套逻辑；338 测试 |
| 6 | `verify_launch_env.py --dcc houdini` | 值真的到达 DCC 进程（hython 里打 `os.environ`） |
| 7 | `+` → `Will create 5 folders · will write 2 overrides` → Create | 预览 = 真调用，基线只写不可推导项 |
