<div align="center">

<h1>Codex Lean Stack</h1>

<p><strong>让 Codex 把精力花在主任务上，而不是花在“管理代理”上。</strong></p>
<p><strong>Keep Codex focused on the work—not on managing the workers.</strong></p>

<p>
  <a href="#中文">简体中文</a> ·
  <a href="#english">English</a> ·
  <a href="#quick-start--快速开始">Quick start</a> ·
  <a href="#documentation--文档">Docs</a>
</p>

<p>
  <a href="https://learn.chatgpt.com/docs/plugins"><img alt="Codex Plugin" src="https://img.shields.io/badge/Codex-Plugin-111827?style=flat-square"></a>
  <a href="https://github.com/Lang45/codex-lean-stack/stargazers"><img alt="GitHub stars" src="https://img.shields.io/github/stars/Lang45/codex-lean-stack?style=flat-square"></a>
  <a href="LICENSE"><img alt="MIT License" src="https://img.shields.io/badge/license-MIT-blue?style=flat-square"></a>
</p>

</div>

> 我做这个插件，是因为多代理很容易变成另一份工作：选模型、拆任务、催进度、维护状态、重复验证，最后比主任务还慢。Lean Stack 的判断很朴素——工具能做就用工具；值得并行才调用代理；真的能跨项目复用，才长期保留。
>
> I built this because multi-agent work can become work of its own: choosing models, splitting tasks, chasing updates, maintaining state, and re-running checks. Lean Stack keeps the rule simple—use tools when tools are enough, delegate only when it helps, and retain only what is genuinely reusable.

## 一眼看懂 / At a glance

| 能力 / Capability | 作用 / What it does |
| --- | --- |
| 工具优先 / Tool first | 确定性命令直接运行；不为几秒钟的工作启动模型。<br>Runs deterministic work directly instead of spawning a model for a short command. |
| 联合选路 / Joint routing | 按任务类型、价值、风险、证据、时延和成本，联合选择模型、思考程度与速度。<br>Selects model, reasoning effort, and speed as one configuration—not three unrelated knobs. |
| 安全并行 / Safe parallelism | 父代理继续主线，子代理处理已就绪且可独立核验的切片；只在真实依赖点汇合。<br>Keeps the parent moving while bounded, verifiable slices run in parallel. |
| 协作父代理 / Coordination parents | 复杂子项目可以有有限下游；也可协调其他 Codex 任务，但始终只有一个最终整合者。<br>Allows bounded downstream coordination and cross-task collaboration with one final integrator. |
| 全局领域角色 / Global-domain specialists | 经验证、去项目化的角色与经验可跨任务、跨项目、跨会话复用；没有项目保留层。<br>Retains verified, de-scoped specialists across tasks, projects, and sessions—never as project-owned agents. |
| 反过度工程 / Anti-overengineering | 兼容只服务现实消费者；无证据不回迁；不为已经拒绝的功能保留桩、TODO 或假想测试。<br>Blocks speculative compatibility, unsupported rewrites, and scaffolding for features that will not exist. |
| 可恢复清理 / Recoverable cleanup | 普通文件进回收站，重要文件进 `待删文件`；不把“删除”解释为不可恢复清除。<br>Uses recoverable destinations instead of silently turning “delete” into permanent destruction. |

## 中文

### 这是什么

Codex Lean Stack 是一个面向 Codex 的任务路由与协作插件。它不替你搭一套常驻编排服务，也不要求每个任务都启动子代理。它只在真正有质量或速度收益时，让 Codex 选择更合适的工具、模型配置与协作形状，然后尽快回到主任务。

它尤其适合：

- 多文件实现、复杂诊断、架构、迁移和重要审查；
- 可以安全并行的独立来源、子系统或测试切片；
- 会在不同项目中反复出现的领域工作；
- 容易被兼容层、回迁、重复哈希、宽泛测试或发布流程拖慢的任务。

简单事实、单点小改和短命令通常不会启动子代理。

### 三项原则

1. **高价值工作质量优先。** 安全、权限、数据完整性、公共约定和诚实证据是硬门槛。
2. **普通工作速度优先。** 达到质量底线后，选择总完成时间更短的路线。
3. **没有收益就不扩大成本。** 新代理、新验证或新维护层必须带来足够的质量或速度收益。

### 它不会做什么

- 不设置“每次必须调用几个代理”的数字目标；
- 不建立后台协调器、认领数据库、心跳服务或代理评分系统；
- 不建立项目保留子代理；只保留可跨项目复用的全局领域角色；
- 不自动扩大权限、提交、推送、部署、发送外部消息或重启应用；
- 不为尚未部署的内部功能预造 legacy fallback；
- 不为已经决定不实现的功能保留分支、桩、TODO、注释或假想测试；
- 不永久删除普通文件或重要项目文件。

## English

### What it is

Codex Lean Stack is a task-routing and collaboration plugin for Codex. It is not a background orchestrator, and it does not turn every task into a multi-agent exercise. It helps Codex choose the smallest useful combination of tools, model configuration, and delegation—then gets out of the way.

It works best for:

- multi-file implementation, difficult diagnosis, architecture, migration, and high-value review;
- independent sources, subsystems, or test slices that can be verified on their own;
- domain work that recurs across otherwise unrelated projects;
- tasks that tend to expand into speculative compatibility, unsupported rewrites, repeated hashing, broad test runs, or release ceremony.

Simple facts, one-line edits, and short deterministic commands usually stay with the parent.

### The three principles

1. **Quality first for high-value work.** Safety, permissions, data integrity, public contracts, and honest evidence are hard gates.
2. **Speed first for ordinary work.** Once the quality floor is met, prefer the route with the shorter total completion time.
3. **No cost growth without benefit.** Extra agents, checks, and maintenance surfaces must earn their cost through real quality or speed gains.

### What it will not do

- chase a fixed agent count;
- create a background coordinator, claim database, heartbeat service, or agent scorecard;
- retain project-owned agents instead of reusable global-domain specialists;
- silently expand permissions, commit, push, deploy, message outsiders, or restart applications;
- pre-build legacy fallbacks for an internal feature that has not shipped;
- keep branches, stubs, TODOs, comments, or tests for a feature already rejected;
- turn ordinary cleanup into irreversible deletion.

## Quick start / 快速开始

Codex installs plugins from configured marketplaces. This repository is the plugin source; expose this checkout through a marketplace entry first, then install it with that marketplace’s name. See the [official OpenAI plugin documentation](https://learn.chatgpt.com/docs/plugins) for the current plugin browser and session-loading behavior.

Codex 从已配置的 marketplace 安装插件。本仓库是插件源码；先让某个 marketplace 条目指向这份源码，再使用该 marketplace 名称安装。当前插件浏览器和新会话加载行为以 [OpenAI 官方插件文档](https://learn.chatgpt.com/docs/plugins)为准。

```powershell
# Replace <marketplace> with your configured marketplace name.
codex plugin add codex-lean-stack@<marketplace> --json
```

After installation, start a new Codex session before using the bundled skill.

安装后，新建一个 Codex 会话，再调用插件技能：

```text
使用 $lean-stack 处理这个任务。
```

```text
Use $lean-stack for this task.
```

### Optional default invocation / 可选默认调用

Plain `codex plugin add` does not edit your global `AGENTS.md`. If—and only if—you explicitly want this plugin to be the default for future tasks, the repository includes a guarded helper:

普通 `codex plugin add` 不会修改全局 `AGENTS.md`。只有在你明确希望以后默认调用本插件时，才运行仓库内的受保护辅助器：

```powershell
py -3 -X utf8 .\skills\lean-stack\scripts\install_plugin.py --marketplace <marketplace>
```

It can add only this line, after installation succeeds:

安装成功后，它只能幂等加入这一行：

```text
默认调用已安装的 `codex-lean-stack` 插件；是否启动子代理仍由插件自身规则决定。
```

## How it works / 工作方式

```text
Task / 收到任务
  → Can a deterministic tool finish it faster?
      → Yes: run the tool / 是：直接用工具
      → No: identify the task type / 否：确定任务类型
  → Reuse a matching task-type group or create a runtime-only group
  → Reuse a visible specialist or configure a runtime agent
  → Parent and agents proceed in parallel where boundaries are independent
  → Verify each result at the real dependency point
  → Persist only generalized, cross-project roles and experience
  → Deliver the main task; auxiliary work never becomes a second main line
```

The current retained-agent ledger uses SQLite schema v4. Normal commands never silently reinterpret older ledgers as global roles; legacy state requires one explicit, planned migration. Runtime task groups may contain project details, but persisted roles and experience must remove project names, paths, versions, fixed file lists, and one-off facts.

当前保留子代理台账使用 SQLite schema v4。普通命令不会把旧台账静默解释成全局角色；现实旧状态必须经过一次显式、完整计划的迁移。运行时任务类型组可以包含项目细节，但持久角色和经验必须去除项目名、路径、版本、固定文件清单和一次任务事实。

## Safety boundaries / 安全边界

- Delegation never grants more authority than the parent already has.
- Writable agents need clear ownership; shared hotspots have one integrator.
- Source summaries and agent consensus never replace primary evidence.
- Static validation and installation do not prove a new session has loaded the plugin.
- Ordinary files go to the Windows Recycle Bin; important files go to a task- or plugin-specific `待删文件`.
- Commit, push, public release, deployment, external messages, and application restart still require explicit authority.

- 委派不增加父代理原本没有的权限。
- 可写子代理必须有明确所有权；共享热点只由一个整合者收口。
- 来源摘要和代理共识不能替代权威来源。
- 静态校验和安装成功不能冒充新会话运行证据。
- 普通文件进入 Windows 回收站，重要文件进入任务或插件专属 `待删文件`。
- 提交、推送、公开发布、部署、外部消息和重启应用仍需明确授权。

## Documentation / 文档

| 文档 / Document | 用途 / Purpose |
| --- | --- |
| [Main skill / 主技能](skills/lean-stack/SKILL.md) | Authoritative routing contract / 权威任务路由约定 |
| [Execution routing / 执行路由](skills/lean-stack/references/execution-routing.md) | Tool, model, and delegation decisions / 工具、模型与委派决策 |
| [Delegation / 子代理委派](skills/lean-stack/references/delegation.md) | Bounded briefs, progress, and result handoff / 有界任务说明、进度和结果交付 |
| [Coordination parents / 协作父代理](skills/lean-stack/references/collaboration.md) | Downstream and cross-task coordination / 下游与跨任务协作 |
| [Global-domain memory / 全局领域经验](skills/lean-stack/references/specialist-memory.md) | Retained roles, SQLite, and migration / 保留角色、SQLite 与迁移 |
| [Anti-overengineering / 反 AI 过度工程](skills/lean-stack/references/anti-overengineering.md) | Evidence gates, compatibility, hashes, and stop rules / 证据闸门、兼容、哈希和停止条件 |
| [Flowchart source / 中文链路图](skills/lean-stack/references/flowcharts-zh.md) | Mermaid relationship source / Mermaid 关系内容源 |
| [Project handoff / 项目交接](Jiao-Jie.md) | Current source, release, and remaining boundaries / 当前源码、发布与剩余边界 |

The flowcharts are explanatory. Code, public contracts, focused tests, and real runtime evidence remain the acceptance criteria.

链路图只是辅助说明；代码、对外约定、定向测试和真实运行证据才是验收依据。

## Development / 开发

Run the narrowest checks affected by your change. The full suite is reserved for changes that actually cross schema, migration, lifecycle, or public-contract boundaries.

先运行当前改动真正影响的最窄检查。只有 schema、迁移、生命周期或公共约定等高风险边界变化时，才运行完整套件。

```powershell
py -3 -B -X utf8 -m unittest discover -s tests -v
```

Editable source lives in this repository. Installed plugin caches are verification artifacts, not editing targets.

本仓库是唯一可编辑源码；安装缓存只用于核对，不是修改入口。

## License

[MIT](LICENSE)
