# Codex子代理调用与精简流程

插件标识：`codex-lean-stack`

## 当前版本 4.1.0

由于`gpt-6-astra` 过于昂贵以及研究发现：额度消耗的真正占大头是父代理每次工具往返都要重新带入的上下文。
所以我以后主要改为父代理用 Sol，gpt-6-astra作为可以调用的子代理专家。

1. 派出的 `gpt-6-astra` 子代理思考程度最高为 `xhigh`；`max` 和 `ultra` 不是 Astra 子代理的可用组合，角色生成器会在落盘前拒绝。
2. Sol 父代理仍可在遇到自身难以可靠解决的具体专家问题时派发该 Astra 切片。


## 中文

### 调用前

1. **首条说明先到。** 先说明理解、立即动作和必要范围；过程中报告有效进展，最终交付入口、验证对象与剩余问题。
2. **锚点只留剩余要求。** 已交付事项退出；纠正只重开受影响项，“继续”不复活历史待办。
3. **工具先行。** 短命令、批量查询和确定性工作直接用工具，不启动只会代跑命令的模型子代理。
4. **复杂 PowerShell 及时落到脚本。** 多层引号、JSON/正则或多行逻辑使用任务专属 `.ps1`；确认转义失败后只修同一脚本，不反复改 one-liner。
5. **三原则决定调用。** 高价值工作先守必要质量和决定性证据；质量达标后比较父代理继续工作的 token、时间、返工与子代理启动、交流、整合、核验组成的总成本，成本相近再比速度。维护后的明显模型价差直接支持范围清楚、短输出、易增量核验的低成本 GPT-5.6 切片取得正向收益判断。
6. **联合选配和能力复用。** 不设调用数量；按任务类型和任务类型组识别能力族，复用保留子代理并联合选择模型、思考程度和速度。新选配全部默认标准速度；Sol 遇到确需专家的具体困难时可派范围明确的 Astra 子任务，不升级整批；派出的 Astra 思考程度最高为 `xhigh`。
7. **上下文与交接按需。** 独立任务优先 `fork_turns="none"`；只传当前约束和证据。项目交接见[可执行项目交接](skills/lean-stack/references/project-handoff.md)。

### 运行中

1. **内部交流只服务真实依赖。** 证据能解锁下一动作、需要纠偏或出现风险时才发消息。
2. **子代理公开实际配置。** 在自己的可见回复声明名称、模型、思考程度和速度；普通任务不再向父代理重复发送相同四行。
3. **关键步骤只为真实依赖。** 只有中间结果会解锁下一动作时才报告一次并继续；不发送定时心跳、纯确认消息或普通过程复述。
4. **父代理不中断主线。** 父代理立即推进，只在真实依赖点等待，不完整重做已核验结果。
5. **持续多工作流任务尽早派发并重判。** 新范围、独立困难或压缩后的多个就绪工作流会使旧的直接处理判断失效；父代理继续工作的成本也进入新路线比较。
6. **协作保持所有权。** 变体只为真实改进；子代理可以成为协作父代理；可写任务使用不重叠写入范围，结果以 `SOURCE_COVERAGE` 说明来源覆盖。

### 收口与复用

1. **每个子代理独立交付。** commentary 不是最终结果；具体缺口最多补问一次，否则关闭或只改派缺口。
2. **子代理会积累经过采用的经验。** 用 UUID `run_id` 记录明确成功或失败，`ensure` 和 `improve` 各尝试一次；每个能力族只保留一个全局领域角色，没有项目保留层。
3. **累计两次明确失败后永久移除角色资料。** 运行中、中断、未采用、用户停止或结果未定不算失败。
4. **初版不是完成。** 实现继续到获准的运行、检查、修补和真实入口；只读或方案任务按用户指定范围停止。
5. **统计只读。** `status --for-dashboard` 输出当前聚合；`--watch-seconds 2` 仅在前台刷新。

### 精简与安全

1. **兼容只服务现实消费者。** 被拒绝的功能不留分支、桩、TODO 或假想测试。
2. **测试只覆盖受影响范围。** 复用未变化证据，必要时做真实运行验收。
3. **同一规则一个权威源。** README 只解释用户可见行为，详细规则在技能和 references；没有后台编排系统。
4. **清理与权限守界。** 普通文件进入 Windows 回收站；安全、权限、数据完整性和不可逆损失保留相称保护，委派不增加外部权限。

### 调用流程

```text
收到任务 → 工具能确定完成则直接执行
→ 否则判断有收益的独立切片
→ 复用或定制合适子代理
→ 父代理并行推进并在真实依赖点整合
→ 核验、记录可复用经验、交付主任务
```

### 不调用代理的情况

- 工具更快且足够可靠；
- 输入未就绪或任务严格依赖前一步；
- 写入冲突无法隔离，或缺少所需能力、工具、权限与运行容量；
- 只会重复已有工作；
- 交接、整合与增量核验明显超过切片本身，或新增成本显著且没有必要质量收益。



## 安装与使用 / Install and use

Codex 从 marketplace 安装插件；本仓库是可编辑源码：

```powershell
codex plugin add codex-lean-stack@<marketplace> --json
```

新建 Codex 会话后调用：

```text
使用 $lean-stack 处理这个任务。
Use $lean-stack for this task.
```

当前加载规则见 [OpenAI 官方插件文档](https://learn.chatgpt.com/docs/plugins)。
See the [official OpenAI plugin documentation](https://learn.chatgpt.com/docs/plugins).

普通 `codex plugin add` 不会修改全局 `AGENTS.md`。Plain `codex plugin add` does not edit global `AGENTS.md`.
只有明确要求默认调用时才运行：

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
- [版本说明 / Changelog](CHANGELOG.md)

本仓库是唯一可编辑源码，安装缓存只用于核对。提交前运行当前改动真正影响的最窄约定一致性测试。

## License

[MIT](LICENSE)
