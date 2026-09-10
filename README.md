# Codex子代理调用与精简流程

插件标识：`codex-lean-stack`

主技能是简短入口：先决定工具或子代理路线，只在实际委派、写入、维护经验等动作发生时读取
相应细则。已有规则在当前上下文复用，简单修改不预读全部手册。

## 中文

### 调用前

1. **首条说明先到，过程与结果说清。** 每次要求先说明理解与动作，持续实现也交代具体进展；最终说明改动原因、实际入口、验证对象与剩余问题，内部少发确认消息不等于让用户一直等待。
2. **锚点只保留剩余要求。** 已完成并在上一条回复中交付的要求自动退出；纠正只重新打开受影响项，“继续”只恢复尚未完成或尚未交付的事项。
3. **工具先行。** 短命令、批量查询和步骤确定的工作直接用工具或持续终端完成，不启动只会代跑命令的模型子代理。
4. **复杂 PowerShell 及时落到脚本。** 简单命令仍内联；多层引号、嵌套 JSON/正则、反引号、多行逻辑或复杂变量插值直接写入任务专属临时 `.ps1`。首次失败确认是解析或转义后就停止改写 one-liner，后续只编辑同一脚本；脚本不入库、不含秘密，清理时进入 Windows 回收站或任务专属 `待删文件`。
5. **三原则决定调用。** 高价值工作先守必要质量和决定性证据；质量达标后先比较父子输入输出、交流、核验和返工组成的全任务总成本，成本相近才比较总完成时间。当前用户明确速度或期限要求时再提高速度权重；没有必要质量收益时，不为单纯提速大幅增费。正向寻找能替代父代理阅读、实现或分析的切片，端到端任务也可委派。
6. **不追求代理数量。** 插件使用运行环境的真实并发容量，但容量只是上限，不设置“必须调用几个”或“必须占满”的目标。
7. **按能力族匹配，不按动作拆窄。** 同一可复用能力族内的调查、诊断、实现、修复、测试或验收，只要工具、权限、风险与证据形状兼容，就优先匹配已有保留角色；项目、框架、动作动词、交付名称和一次性成功条件不另建窄角色。只读边界不因范围放宽而改变。描述不足或准备因无匹配而新建角色前，通过 `status --for-routing` 核对一次目录；角色未加载或配置需要适配时，用 `recall --name <角色名>` 取得经过身份核验的职责、配置与有界经验。
8. **联合选择完整配置。** 所有父代理按三原则比较完整的“模型 + 思考程度 + 速度”组合，三个字段可以一起调整，同一模型不固定一档；Luna、Terra、Sol 是通常候选，Sol 可端到端承担复杂高价值工作。Astra 只在额外决定性质量或更少返工、token 等使全任务总成本更低时考虑，不能只凭更快。新选配全部默认标准速度；只有当前用户明确速度或期限要求且完整路线有收益时才用快速。已有显式快速配置保留真实值，不适配时只调整本次调用。
9. **交接能直接接着做。** 跨项目交接保留用户操作验收、权威路径、已否定路线和末尾唯一当前快照；具体规则见[可执行项目交接](skills/lean-stack/references/project-handoff.md)。
10. **上下文按任务需要继承。** 独立窄任务优先 `fork_turns="none"`；依赖前面决策时才加历史。新上下文任务说明显式携带职责、工具与安全边界，继承父级历史也不自动获得父级编排权限。

### 运行中

1. **内部交流只服务真实依赖。** 只有证据会解锁父代理或队友下一动作、需要输入纠偏，或出现风险和阻断时才发内部消息；普通过程随最终回复交付，不重复汇报。
2. **子代理公开实际配置。** 每次启动新子任务时，子代理在自己的可见 `commentary` 和最终回复顶部声明名称、模型、思考程度和速度；普通任务不再向父代理重复发送相同四行，也不索要确认。
3. **关键步骤只为真实依赖。** 只有中间结果会解锁下一动作时才报告一次并继续；不发送定时心跳、纯确认消息或普通过程复述。
4. **父代理不中断主线。** 子代理运行时父代理继续约束、冲突、必要核验、集成或共享热点，不全面重做证据充分的子任务；只在下一步真实依赖某个结果时等待，不为“收齐所有代理”而空等。
5. **持续多工作流任务尽早派发。** 多个独立就绪切片能替代父代理实际研究、实现或验收时，在父代理深入读取额外来源族或开始实现前，派发全部当前有收益且互不冲突的 GPT-5.6 切片；数量随真实工作流、边际收益与容量变化，不设最低数量或逐片量化门槛，无法精确量化本身不能否决调用。每个新增同类型切片仍按全任务总成本、必要质量收益，以及成本相近且用户有当前期限要求时的总完成时间判断。
6. **变体只为真实改进。** 只有基准代理确有改进空间时才建立变体，并用完整的模型、思考程度和速度组合完成真实任务后比较，不为制造实验而改一个参数。
7. **子代理可以成为协作父代理。** 有边界的子项目包含多个独立切片时，一个子代理可在获批范围内协调下游；下游各自提交结果，最上层仍只有一个最终整合父代理。
8. **可以协作其他 Codex 父代理任务。** 在当前授权和三项原则内可读取、调用或新建用户可见的 Codex 任务，但必须指定唯一整合者，并与内部父子消息严格分开。
9. **并行写入有明确所有权。** 不重叠文件可以并行修改，共享清单、接口或数据库最后集中整合；没有独立工作树时，同一物理文件只允许一个实际写入者。
10. **委派替代重复劳动。** 工具先定位并批量读取独立来源，在工具侧筛选和限制输出预算，再在昂贵父代理大量预读或生成前交给合适角色；已落盘结果只回定位、关键差异与验证。父代理按风险核验关键差异，不全面重做；按父子合计消耗、交流与返工评估成本。
11. **依赖证据才直达队友。** 只有真正解锁下一动作的来源和发现才发内部消息；影响职责、共享写入或安全的变化同时告知父代理裁决，不等待确认，也不代交队友最终结果。

### 收口与复用

1. **每个子代理独立交付。** 子代理达到成功条件或停止条件后在自己的线程提交结果，普通子代理不能代交、隐藏或汇总其他子代理的最终回复。
2. **竞争不会丢掉合格成果。** 复制和变体先分别交付并被采用，再比较哪种配置更适合以后复用；竞争只选未来保留者，不抹掉本轮有效结果。
3. **只保留全局领域角色。** 角色持久化前删除项目名、路径、版本和一次任务事实，每个领域保留一个可跨任务、跨项目、跨会话复用的休眠角色，没有项目保留层。
4. **子代理会积累经过采用的经验。** 区分规则缺陷、执行失误和原因未明；记录情境、做法、证据与例外，扩大适用范围须有独立样本。未采用路线只留核验后的短避坑结论及重开条件；用户否定的子代理结果不得回流。仍用现有追加与纠正机制，不引入优化器或训练任务。
5. **任务结果只记录明确完成。** 启动前分配 UUID `run_id`；成功只有在达到条件、结果被采用且线程进入 Done 后才记录，失败只有整个任务已有明确失败结论时才记录。运行中、中断、未采用、用户停止或否定、工具缺失后停止及结果未定都不计失败。累计两次明确任务失败后，永久移除该角色的 TOML、身份、全部成功/失败运行、原始经验、纠正事件与摘要；不保留退役角色、收据或恢复入口。一次失败的角色仍可由总尝试与失败数区分“从未调用”和“尚未成功”。
6. **经验写入不阻塞主任务。** `ensure` 和 `improve` 只各做一次短提交，遇到忙锁、结构漂移、权限或文件身份问题立即跳过，不排队、不轮询、不重试。
7. **保留角色不会常驻耗费模型。** 跨会话保留的是休眠 TOML 配置和去敏经验，当前子代理线程完成后正常结束，未来任务需要时才重新生成。
8. **初版不等于完成。** 实现任务持续到已授权的运行或测试、检查结果、修复本次失败并交付实际入口；用户明确只读、只要方案或先审阅时，按该范围停止。
9. **生命周期统计可以只读查看。** `status --for-dashboard` 输出一次当前保留角色、总尝试、成功、失败、经验与纠正事件聚合；追加 `--watch-seconds 2` 会在前台每两秒输出一条 NDJSON 快照，按 `Ctrl+C` 结束。永久移除的角色不会出现在后续快照中；该功能不创建后台任务，也不代表 Codex 插件卡已经自动刷新。

### 精简与安全

1. **兼容只服务现实消费者。** 没有已安装或已发布版本、真实调用方、用户数据、公共约定或持久状态，就不写 legacy reader、双写、永久别名或回退分支。
2. **决定不实现的功能不留维护物。** 不为被拒绝的功能保留分支、桩、TODO、解释其缺席的注释、假想测试、预留字段或空目录。
3. **哈希只在必要位置计算一次。** 哈希只服务所有权、CAS、迁移、恢复、真实产物和最终安装一致性；同一输入未变化时复用已有结果，不反复散列全树。
4. **测试只覆盖受影响边界。** 迭代时先跑最窄检查，代码、依赖、配置和环境没变就复用通过证据，只有真实高风险边界变化才扩大验证。复核修补后做增量检查；剩余疑问需要真实运行时，进入已授权的窄验证，不循环追加静态意见。
5. **同一规则只有一个权威源。** README 只解释用户需要知道的行为，详细规则留在技能和参考文档，不在 UI、流程图、测试和交接中逐字维护多份副本。
6. **没有后台编排系统。** 插件不建立认领数据库、锁租约、代理评分、心跳服务、守护进程或第二套任务状态机。
7. **一般清理保持可恢复，角色生命周期按明确合同永久移除。** 普通文件进入 Windows 回收站，重要文件进入任务或插件专属 `待删文件`；保留角色只有累计第二次明确失败，或严格匹配零经验零尝试的手动删除条件时，才永久移除全部角色资料。委派不自动获得提交、推送、部署、外部消息或重启权限。
8. **消融只在你明确要求时启动。** 说“进行消融实验”或明确要求精简当前代码/设计后，一个不含作者推理历史的新上下文每次真实删除、内联或合并一个候选，并用同一验收集比较前后；改名、搬移或再包一层不算精简，核心功能和设计意图先冻结。防御候选同时按发生频率、影响、可检测性和人工恢复成本判断：可检测、可人工修复的极低频问题不默认增加自动补偿或自愈，安全、权限、数据完整性或不可逆损失仍保留相称防护。

### 调用流程

```text
收到任务
→ 确定性工具能更快完成？
  → 能：父代理直接用工具
  → 不能：完成一次调用判断
→ 确定具体任务类型和运行时任务类型组
→ 复用保留子代理，或联合配置运行时新子代理
→ 子代理在自身界面声明配置；父代理与独立子任务并行推进
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
- 只会重复已有工作，不能增加必要质量、证据或降低全任务总成本；
- 新增调用的交接、等待和核验成本高于收益；
- 启动后只能等待，不能完成真实任务。

## English

The main skill is a short entry point. Load detailed references only when delegation, writes, or experience
maintenance needs them, and reuse unchanged instructions already in context.

### Before delegation

1. **A fast first explanation, clear progress and delivery.** Explain understanding and action first, report concrete progress during implementation, and finish with changes, reasons, the actual entry point, verification scope, and remaining issues; sparse internal acknowledgements do not mean leaving the user uninformed.
2. **The anchor contains only remaining work.** A completed requirement leaves the active list after delivery; a correction reopens only affected work, and “continue” resumes only unfinished or not-yet-delivered items.
3. **Tool first.** Run deterministic commands, batch queries, and long predictable processes directly instead of spawning a model to relay an exit code.
4. **Move complex PowerShell into a script.** Keep simple commands inline; use a task-scoped temporary `.ps1` for nested quoting, JSON/regex, backticks, multiline logic, or complex interpolation. After the first confirmed parse or escaping failure, stop rewriting the one-liner and edit the same script; keep it out of the repository and free of secrets, then move it recoverably to the Windows Recycle Bin or a scoped `待删文件` when cleaning up.
5. **The three principles decide.** Preserve required quality and decisive evidence first, especially for high-value work. Once quality is sufficient, compare whole-task parent-and-child cost before elapsed time. Raise speed only when costs are close or the user states a current deadline or speed preference; do not pay substantially more merely to go faster without a required quality gain. Delegate ready end-to-end reading, implementation, and analysis slices that can replace parent work.
6. **Capacity is not a quota.** Use available runtime capacity without targeting a fixed agent count or filling every slot.
7. **Match capability families, not narrow action names.** Reuse a retained role for compatible investigation, diagnosis, implementation, repair, testing, or acceptance within the same capability family. A project, framework, action verb, deliverable label, one-off success condition, or configuration tier does not create a new narrow role. Split only for incompatible tools, write authority, safety risk, or decisive evidence; broader matching never grants a read-only role write access. Check `status --for-routing` once when descriptions are insufficient, and use `recall --name <role-name>` for a verified unloaded role or configuration adaptation.
8. **Select one complete configuration.** Every parent compares complete model, reasoning, and speed combinations under the three principles. Luna, Terra, and Sol are the usual candidates; Sol can own complex high-value work end to end. Use Astra only for additional decisive quality or a lower whole-task cost through less rework or fewer tokens, not merely because it is faster. New selections default to Standard speed, including Luna. Use Fast only for an explicit current deadline or speed request when the complete route benefits; preserve an existing explicit Fast setting and adapt only the current call when it no longer fits.
9. **Make handoffs actionable.** Preserve user-operation acceptance, authoritative paths, rejected routes, and one current snapshot; see [project handoffs](skills/lean-stack/references/project-handoff.md).
10. **Inherit only useful context.** Prefer `fork_turns="none"` for independent bounded tasks and add history only when prior decisions matter. Include task-specific tool, safety, and ownership limits explicitly; inherited orchestration instructions do not grant the parent's authority.

### While agents run

1. **Internal messages serve real dependencies.** Send one only when evidence unlocks the parent or a teammate, input needs correction, or a risk or blocker appears; ordinary process arrives in the final result.
2. **Agents disclose configuration visibly.** Every new subtask shows name, model, reasoning effort, and speed in its own commentary and again at the top of its final result. Ordinary tasks do not repeat the same four lines internally or request confirmation.
3. **Key steps require dependencies.** Report a key step only when its intermediate result unlocks another action, then continue. Send no heartbeat, acknowledgement loop, or routine process recap.
4. **The parent keeps moving.** Continue main-line work and wait only at a real dependency instead of waiting merely to collect every agent.
5. **Dispatch sustained parallel workflows early.** When multiple independent ready slices can replace the parent's research, implementation, or acceptance work, dispatch all currently beneficial, non-conflicting GPT-5.6 slices before the parent deep-reads additional source families or begins implementation. The count follows actual workflows, marginal benefit, and runtime capacity; there is no minimum count or per-slice quantified-savings threshold, and inability to quantify precisely is not a veto. Each additional same-type slice still follows whole-task cost, required quality, and, when costs are close and the user has a current deadline, completion time.
6. **Variants must earn their place.** Create a variant only for a plausible improvement, run a real task, and compare the complete configuration rather than changing one knob for appearance.
7. **Bounded coordination parents.** A scoped subproject may coordinate downstream agents, while every child keeps its own result and one top-level parent owns the final integration.
8. **Cross-task parent collaboration.** Read, continue, or create visible Codex tasks within current authority, with one integrator and no confusion with internal parent-child messaging.
9. **Writable work has ownership.** Parallelize non-overlapping files, integrate shared hotspots once, and allow one real writer per physical file unless genuine worktree isolation exists.
10. **Source coverage is explicit.** Batch independent reads, filter and budget output in tools, and return `SOURCE_COVERAGE` with the snapshot, coverage level, and remaining gap instead of flooding the parent with raw logs.
11. **Only dependency evidence goes directly to teammates.** Send sourced findings internally only when they unlock a next action; route responsibility, shared-write, and safety conflicts to the parent without acknowledgement loops or duplicate final results.

### Closing and reuse

1. **Each agent submits its own result.** Ordinary agents cannot hide, replace, or submit another agent's final response.
2. **Competition preserves useful output.** Copies and variants deliver first; competition selects the future retained configuration without discarding accepted current results.
3. **Retention is global-domain only.** Remove project names, paths, versions, and one-off facts before keeping one dormant specialist per reusable domain; there is no project-retention layer.
4. **Accepted work becomes experience.** Generalize, redact, deduplicate, and append adopted methods and failure-avoidance lessons to SQLite; corrections remain append-only and auditable.
5. **Record only explicit completed outcomes.** Allocate UUID `run_id` before a retained-role task. Record success only after completion, adoption, and Done; record failure only when the whole task has a decisive failed outcome. Running, interrupted, unadopted, user-stopped or rejected, tool-blocked, and undetermined calls are not failures. After two cumulative explicit task failures, permanently remove the role TOML, identity, every success/failure run, raw experience, correction, and summary. No retired-role record, receipt, or restore path remains. Attempt and failure totals can still distinguish a never-invoked role from one with a single failure before removal.
6. **Persistence never blocks delivery.** Try `ensure` and `improve` once each, then skip immediately on locks, schema drift, permission, or file-identity problems.
7. **Retained agents do not stay alive.** Only dormant TOML configuration and redacted experience persist; runtime threads end normally and consume no continuing model calls.
8. **The first implementation is intermediate.** Continue through authorized execution or tests, inspection, repair of failures caused by the change, and delivery of the real entry point. Respect an explicit read-only, proposal-only, or review-first request.
9. **Lifecycle aggregates are read-only and observable.** `status --for-dashboard` returns one current-retained-role, attempt, success, failure, experience, and correction snapshot. Permanently removed roles disappear from later snapshots. Add `--watch-seconds 2` for foreground NDJSON every two seconds and stop it with `Ctrl+C`; this creates no background task and does not claim automatic Codex plugin-card refresh.

### Process removal and safety

1. **Compatibility needs a real consumer.** No shipped version, caller, user data, public contract, or persistent state means no legacy reader, dual write, permanent alias, or fallback branch.
2. **Rejected features leave no scaffolding.** Keep no branch, stub, TODO, absence comment, speculative test, reserved field, or empty directory for a feature that will not exist.
3. **Hash only risk-relevant targets once.** Reuse results for unchanged inputs and reserve hashing for ownership, CAS, migration, recovery, real artifacts, and final install parity.
4. **Run only affected checks.** Reuse unchanged evidence and broaden validation only when the changed behavior or risk requires it. Check review fixes incrementally and move to authorized runtime validation when more static opinions cannot resolve the remaining question.
5. **Keep one authoritative source.** README explains the user-facing behavior while detailed rules remain in the skill and focused references.
6. **No background orchestrator.** The plugin creates no claim database, lease system, scorecard, heartbeat service, daemon, or second task state machine.
7. **General cleanup remains recoverable; the explicit role-lifecycle contract is permanent.** Ordinary files go to the Windows Recycle Bin and important files go to a scoped `待删文件`. A retained role is permanently removed only after its second explicit task failure or when an exact zero-experience, zero-attempt manual-deletion guard passes. Delegation grants no extra external authority.
8. **Ablation is explicitly requested.** When asked to run an ablation or simplify the current code or design, a fresh context with no author rationale removes, inlines, or merges one candidate at a time and reruns the same acceptance checks; renaming, moving, or wrapping it does not count, and core behavior is frozen first. Defensive candidates are judged by frequency, impact, detectability, and manual recovery cost: detectable, manually recoverable outliers do not automatically earn compensation or self-healing, while security, permission, data-integrity, and irreversible-loss protections remain proportionate to impact.

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
- [消融反馈循环 / Ablation loop](skills/lean-stack/references/ablation-loop.md)
- [项目交接 / Project handoff](Jiao-Jie.md)

本仓库是唯一可编辑源码；安装缓存只用于核对。提交代码前运行当前改动真正影响的最窄检查。

This repository is the editable source. Installed caches are verification artifacts. Run the narrowest checks affected by the change before committing.

## License

[MIT](LICENSE)
