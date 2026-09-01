# 代理调用和精简流程

插件标识：`codex-lean-stack`

一个 Codex 插件：决定什么时候直接用工具、什么时候调用代理，并删掉不会提高质量或速度的兼容、验证、哈希和维护流程。

A Codex plugin for deciding when to use tools, when to call agents, and which compatibility, validation, hashing, and maintenance steps should not exist.

## 中文

### 具体功能

1. **先用工具。** 短命令、批量查询和其他确定性工作由父代理直接执行；几秒钟能完成的事不启动模型子代理。
2. **判断是否调用代理。** 只有任务已经就绪、边界清楚、能独立核验、需要持续模型判断，并且能提高质量或缩短时间时才调用。没有固定调用数量；运行环境容量只是上限。
3. **联合选择配置。** 父代理按任务类型、风险、证据、时延和成本，一次确定完整的 `模型 + 思考程度 + 速度`，不按三列分别凑配置。
4. **父代理和子代理并行。** 父代理继续主任务；子代理只处理互不重叠的切片。多个可写任务分别指定文件所有权，共享文件或数据库只由一个整合者收口。
5. **限制交流开销。** 子代理公开实际模型、思考程度和速度，只报告有限关键步骤，不发定时心跳，不等待父代理逐条确认；每个子代理独立提交最终结果。
6. **支持协作父代理。** 符合三项原则且不扩大当前任务权限时，子代理可以协调有限下游，也可以调用其他 Codex 任务；所有路线只保留一个最终整合父代理。
7. **跨项目复用专门角色。** 结果通过核验并被采用后，角色和经验先去掉项目名、路径、版本和一次性事实，再进入全局领域保留。每个领域一个保留子代理，没有项目保留层。
8. **精简无用流程。**
   - 没有已发布版本、真实调用方、用户数据或持久状态，就不写兼容层；
   - 已经决定不实现的功能，不留分支、桩、TODO、注释或假想测试；
   - 哈希只用于所有权、CAS、迁移、恢复和最终安装一致性，同一输入不重复散列；
   - 迭代时只运行受影响的最窄检查，相关代码和环境没变就复用已有结果；
   - 同一规则只设一个权威源，不在 README、UI、流程图和测试里逐字复制。
9. **删除保持可恢复。** 普通文件进入 Windows 回收站，重要文件进入任务或插件专属 `待删文件`。委派不扩大权限，也不自动提交、推送、部署、发送外部消息或重启应用。

### 调用流程

```text
收到任务
→ 确定性工具能更快完成？
  → 能：父代理直接用工具
  → 不能：确定具体任务类型
→ 匹配已有任务类型组，或创建仅用于当前任务的运行时组
→ 复用可见保留子代理，或配置运行时新子代理
→ 父代理与边界独立的子代理并行推进
→ 在真实依赖点核验并整合结果
→ 只有能去项目化的角色和经验才进入全局领域保留
→ 交付主任务
```

### 不调用代理的情况

- 工具可以更快完成；
- 输入或前置条件还没准备好；
- 任务无法独立切分，写入冲突也无法隔离；
- 只会重复已有工作；
- 新增调用的交接、等待和核验成本高于收益。

## English

### Concrete features

1. **Tool first.** The parent runs short commands, batch queries, and deterministic work directly.
2. **One call decision.** An agent is called only for a ready, bounded, independently verifiable task that needs ongoing model judgment and offers a real quality or speed gain. Capacity is an upper bound, not a target.
3. **Joint configuration.** Model, reasoning effort, and speed are selected together for the task type, risk, evidence, latency, and cost.
4. **Parallel work with ownership.** The parent keeps moving. Agents own non-overlapping slices; shared files and databases have one integrator.
5. **Bounded communication.** Agents disclose their effective configuration, report only finite key steps, send no heartbeat, and submit their own final result.
6. **Coordination parents.** A bounded subproject may coordinate downstream agents or other Codex tasks, while one parent remains responsible for the final merge.
7. **Global-domain retention.** Verified roles and experience are stripped of project names, paths, versions, and one-off facts before reuse across tasks, projects, and sessions. There is no project-retention layer.
8. **Concrete process removal.**
   - no real consumer means no compatibility layer;
   - a rejected feature gets no branch, stub, TODO, comment, or speculative test;
   - unchanged inputs are not hashed again;
   - run the narrowest checks affected by your change;
   - keep one authoritative source for each rule.
9. **Recoverable cleanup.** Ordinary files go to the Windows Recycle Bin; important files go to a task- or plugin-specific `待删文件`. Delegation does not grant commit, push, deploy, external-message, or restart authority.

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
- [全局领域经验 / Global-domain memory](skills/lean-stack/references/specialist-memory.md)
- [反 AI 过度工程 / Anti-overengineering](skills/lean-stack/references/anti-overengineering.md)
- [项目交接 / Project handoff](Jiao-Jie.md)

本仓库是唯一可编辑源码；安装缓存只用于核对。提交代码前运行当前改动真正影响的最窄检查。

This repository is the editable source. Installed caches are verification artifacts. Run the narrowest checks affected by the change before committing.

## License

[MIT](LICENSE)
