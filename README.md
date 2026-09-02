# 代理调用和精简流程

插件标识：`codex-lean-stack`

原版 Codex 已经提供并行子代理、自定义 TOML 代理、模型与思考程度配置、运行中纠偏和 Git 工作树；本插件不重复实现这些底层能力，而是补上可审计的调用、交流、收口、经验和精简流程。原版能力见 [OpenAI Codex 子代理文档](https://learn.chatgpt.com/docs/agent-configuration/subagents?surface=app)与[工作树文档](https://learn.chatgpt.com/docs/environments/git-worktrees)。

Stock Codex already provides parallel subagents, custom TOML agents, model and reasoning configuration, runtime steering, and Git worktrees. This plugin adds explicit, auditable rules for calling, communication, closeout, experience, and process removal.

## 中文

### 调用前

1. **工具先行。** 短命令、批量查询和步骤确定的工作直接用工具或持续终端完成，不启动只会代跑命令的模型子代理。
2. **一次调用判断。** 任务已就绪、边界清楚、可独立核验、需要持续模型判断且有质量或速度收益时直接调用，不叠加一串互相重复的审批门槛。
3. **不追求代理数量。** 插件使用运行环境的真实并发容量，但容量只是上限，不设置“必须调用几个”或“必须占满”的目标。
4. **先分任务类型再选代理。** 父代理先判断具体任务类型并匹配或建立运行时任务类型组，之后才复用保留子代理或定制新子代理。
5. **联合选择完整配置。** 模型、思考程度和速度按任务类型、风险、证据、时延和成本一起确定，不按三个单列分别凑数。

### 运行中

1. **Luna 使用真实内部交流。** 新会话第一次使用 `gpt-5.6-luna` 前核对 `agents.enabled` 和实际 `multi_agent_version=v2`；只有父代理收到真实 `agent_message` 才算交流可用，跨任务消息不能冒充。
2. **子代理开头主动声明自己。** 每次启动新子任务时，子代理在内部消息和自己的可见 `commentary` 中声明名称、模型、思考程度和速度，并在最终回复顶部再次声明。
3. **关键步骤有限且不中断工作。** 每个预设关键步骤最多报告一次，发完立即继续，不发送定时心跳、纯确认消息或等待父代理逐条批准。
4. **父代理不中断主线。** 子代理运行时父代理继续需求、架构、集成或共享热点，只在下一步真实依赖某个结果时等待，不为“收齐所有代理”而空等。
5. **同类子任务可以复制加速。** 第二个及后续已就绪的同类型子任务复制组内基准子代理，沿用配置和经验，但分别获得输入、成功条件和权限边界。
6. **变体只为真实改进。** 只有基准代理确有改进空间时才建立变体，并用完整的模型、思考程度和速度组合完成真实任务后比较，不为制造实验而改一个参数。
7. **子代理可以成为协作父代理。** 有边界的子项目包含多个独立切片时，一个子代理可在获批范围内协调下游；下游各自提交结果，最上层仍只有一个最终整合父代理。
8. **可以协作其他 Codex 父代理任务。** 在当前授权和三项原则内可读取、调用或新建用户可见的 Codex 任务，但必须指定唯一整合者，并与内部父子消息严格分开。
9. **并行写入有明确所有权。** 不重叠文件可以并行修改，共享清单、接口或数据库最后集中整合；没有独立工作树时，同一物理文件只允许一个实际写入者。
10. **来源读取有覆盖回执。** 读取会话、文档或日志的子代理返回 `SOURCE_COVERAGE`，明确来源快照、完整或部分覆盖以及剩余缺口，不把大段原始日志塞回父代理。

### 收口与复用

1. **每个子代理独立交付。** 子代理达到成功条件或停止条件后在自己的线程提交结果，普通子代理不能代交、隐藏或汇总其他子代理的最终回复。
2. **竞争不会丢掉合格成果。** 复制和变体先分别交付并被采用，再比较哪种配置更适合以后复用；竞争只选未来保留者，不抹掉本轮有效结果。
3. **只保留全局领域角色。** 角色持久化前删除项目名、路径、版本和一次任务事实，每个领域保留一个可跨任务、跨项目、跨会话复用的休眠角色，没有项目保留层。
4. **子代理会积累经过采用的经验。** 已核验并采用的方法与失败避免信息经过泛化、去敏和去重后追加到 SQLite；被否定经验用纠正事件退出活跃提示，不伪装成物理删除。
5. **存活轮次只记录真实成功。** 只有子任务完成、结果被采用且线程进入 Done 后才用 UUID `run_id` 幂等记录，失败、停止、否定或仍在运行都不计数。
6. **经验写入不阻塞主任务。** `ensure` 和 `improve` 只各做一次短提交，遇到忙锁、结构漂移、权限或文件身份问题立即跳过，不排队、不轮询、不重试。
7. **保留角色不会常驻耗费模型。** 跨会话保留的是休眠 TOML 配置和去敏经验，当前子代理线程完成后正常结束，未来任务需要时才重新生成。

### 精简与安全

1. **兼容只服务现实消费者。** 没有已安装或已发布版本、真实调用方、用户数据、公共约定或持久状态，就不写 legacy reader、双写、永久别名或回退分支。
2. **决定不实现的功能不留维护物。** 不为被拒绝的功能保留分支、桩、TODO、解释其缺席的注释、假想测试、预留字段或空目录。
3. **哈希只在必要位置计算一次。** 哈希只服务所有权、CAS、迁移、恢复、真实产物和最终安装一致性；同一输入未变化时复用已有结果，不反复散列全树。
4. **测试只覆盖受影响边界。** 迭代时先跑最窄检查，代码、依赖、配置和环境没变就复用通过证据，只有真实高风险边界变化才扩大验证。
5. **同一规则只有一个权威源。** README 只解释用户需要知道的行为，详细规则留在技能和参考文档，不在 UI、流程图、测试和交接中逐字维护多份副本。
6. **没有后台编排系统。** 插件不建立认领数据库、锁租约、代理评分、心跳服务、守护进程或第二套任务状态机。
7. **删除保持可恢复。** 普通文件进入 Windows 回收站，重要文件进入任务或插件专属 `待删文件`；委派不自动获得提交、推送、部署、外部消息或重启权限。

### 调用流程

```text
收到任务
→ 确定性工具能更快完成？
  → 能：父代理直接用工具
  → 不能：完成一次调用判断
→ 确定具体任务类型和运行时任务类型组
→ 复用保留子代理，或联合配置运行时新子代理
→ 子代理声明自己；父代理与独立子任务并行推进
→ 只在真实依赖点等待并核验各自结果
→ 复制或变体完成组内收口
→ 能去项目化：保留全局领域角色并追加经验
→ 不能去项目化：只使用本轮结果，不持久化
→ 交付主任务
```

### 不调用代理的情况

- 工具可以更快完成；
- 输入或前置条件还没准备好；
- 任务无法独立切分，写入冲突也无法隔离；
- 只会重复已有工作，不能增加质量、证据或速度；
- 新增调用的交接、等待和核验成本高于收益；
- 启动后只能等待，不能完成真实任务。

## English

### Before delegation

1. **Tool first.** Run deterministic commands, batch queries, and long predictable processes directly instead of spawning a model to relay an exit code.
2. **One call decision.** Delegate a ready, bounded, independently verifiable task when it needs continuing judgment and offers a real quality or speed gain.
3. **Capacity is not a quota.** Use available runtime capacity without targeting a fixed agent count or filling every slot.
4. **Classify before selecting.** Identify the task type and runtime task-type group before reusing a retained agent or configuring a new one.
5. **Select one complete configuration.** Choose model, reasoning effort, and speed together from task type, risk, evidence, latency, and cost.

### While agents run

1. **Verified Luna messaging.** Check `agents.enabled` and the real Luna catalog's `multi_agent_version=v2`; only a received `agent_message` proves internal communication works.
2. **Agents introduce themselves.** Every new subtask discloses name, model, reasoning effort, and speed internally, visibly in its own thread, and again at the top of its final result.
3. **Finite progress messages.** Report each predefined key step at most once, continue immediately, and send no heartbeat or acknowledgement loop.
4. **The parent keeps moving.** Continue main-line work and wait only at a real dependency instead of waiting merely to collect every agent.
5. **Copies accelerate repeated work.** Additional ready tasks of the same type reuse the baseline agent's configuration and experience while keeping separate inputs and acceptance conditions.
6. **Variants must earn their place.** Create a variant only for a plausible improvement, run a real task, and compare the complete configuration rather than changing one knob for appearance.
7. **Bounded coordination parents.** A scoped subproject may coordinate downstream agents, while every child keeps its own result and one top-level parent owns the final integration.
8. **Cross-task parent collaboration.** Read, continue, or create visible Codex tasks within current authority, with one integrator and no confusion with internal parent-child messaging.
9. **Writable work has ownership.** Parallelize non-overlapping files, integrate shared hotspots once, and allow one real writer per physical file unless genuine worktree isolation exists.
10. **Source coverage is explicit.** Reading agents return `SOURCE_COVERAGE` with the snapshot, coverage level, and remaining gap instead of flooding the parent with raw logs.

### Closing and reuse

1. **Each agent submits its own result.** Ordinary agents cannot hide, replace, or submit another agent's final response.
2. **Competition preserves useful output.** Copies and variants deliver first; competition selects the future retained configuration without discarding accepted current results.
3. **Retention is global-domain only.** Remove project names, paths, versions, and one-off facts before keeping one dormant specialist per reusable domain; there is no project-retention layer.
4. **Accepted work becomes experience.** Generalize, redact, deduplicate, and append adopted methods and failure-avoidance lessons to SQLite; corrections remain append-only and auditable.
5. **Only real successes survive.** Record a run idempotently with UUID `run_id` only after completion, adoption, and Done state.
6. **Persistence never blocks delivery.** Try `ensure` and `improve` once each, then skip immediately on locks, schema drift, permission, or file-identity problems.
7. **Retained agents do not stay alive.** Only dormant TOML configuration and redacted experience persist; runtime threads end normally and consume no continuing model calls.

### Process removal and safety

1. **Compatibility needs a real consumer.** No shipped version, caller, user data, public contract, or persistent state means no legacy reader, dual write, permanent alias, or fallback branch.
2. **Rejected features leave no scaffolding.** Keep no branch, stub, TODO, absence comment, speculative test, reserved field, or empty directory for a feature that will not exist.
3. **Hash only risk-relevant targets once.** Reuse results for unchanged inputs and reserve hashing for ownership, CAS, migration, recovery, real artifacts, and final install parity.
4. **Run only affected checks.** Reuse unchanged evidence and broaden validation only when the changed behavior or risk requires it.
5. **Keep one authoritative source.** README explains the user-facing behavior while detailed rules remain in the skill and focused references.
6. **No background orchestrator.** The plugin creates no claim database, lease system, scorecard, heartbeat service, daemon, or second task state machine.
7. **Cleanup remains recoverable.** Ordinary files go to the Windows Recycle Bin; important files go to a scoped `待删文件`, and delegation grants no extra external authority.

## 安装与使用 / Install and use

Codex 从已配置的 marketplace 安装插件。本仓库是插件源码；先让 marketplace 条目指向这份源码，再安装：

Codex installs plugins from configured marketplaces. Point a marketplace entry at this source checkout, then install:

```powershell
codex plugin add codex-lean-stack@<marketplace> --json
```

安装后新建 Codex 会话，再调用：

Start a new Codex session after installation, then invoke:

```text
使用 $lean-stack 处理这个任务。
Use $lean-stack for this task.
```

当前插件浏览器和新会话加载规则见 [OpenAI 官方插件文档](https://learn.chatgpt.com/docs/plugins)。

See the [official OpenAI plugin documentation](https://learn.chatgpt.com/docs/plugins) for the current plugin browser and session-loading behavior.

普通 `codex plugin add` 不会修改全局 `AGENTS.md`。只有明确希望以后默认调用本插件时，才运行：

Plain `codex plugin add` does not edit global `AGENTS.md`. Run the guarded helper only when you explicitly want default invocation:

```powershell
py -3 -X utf8 .\skills\lean-stack\scripts\install_plugin.py --marketplace <marketplace>
```

## 文档 / Docs

- [主技能 / Main skill](skills/lean-stack/SKILL.md)
- [执行路由 / Execution routing](skills/lean-stack/references/execution-routing.md)
- [子代理委派 / Delegation](skills/lean-stack/references/delegation.md)
- [协作父代理 / Coordination parents](skills/lean-stack/references/collaboration.md)
- [全局领域经验 / Global-domain experience](skills/lean-stack/references/specialist-memory.md)
- [可写子代理并行 / Writable parallelism](skills/lean-stack/references/write-parallelism.md)
- [反 AI 过度工程 / Anti-overengineering](skills/lean-stack/references/anti-overengineering.md)
- [项目交接 / Project handoff](Jiao-Jie.md)

本仓库是唯一可编辑源码；安装缓存只用于核对。提交代码前运行当前改动真正影响的最窄检查。

This repository is the editable source. Installed caches are verification artifacts. Run the narrowest checks affected by the change before committing.

## License

[MIT](LICENSE)
