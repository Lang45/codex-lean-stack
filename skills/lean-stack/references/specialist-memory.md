# 保留子代理身份与经验

本分支只处理跨任务复用的保留身份、完成记录和经验。普通 `spawn_agent`、同任务
`followup_task`、临时角色或没有跨任务价值的成功结果不进入本分支；新能力族可独立按需保留身份，已核验并采用的保留身份明确失败可按需记录。身份维护不能成为派发前置，
也不能延迟已经就绪的主任务动作或交付。

辅助脚本是 [agents.py](../scripts/agents.py)。它维护受管 TOML 与 SQLite，不启动、继续或观察
Codex 子代理，也不能证明宿主实际加载了某个身份或经验。
下列相对脚本路径示例只适用于本插件源码仓库根。跨项目调用时，从当前已加载的 `lean-stack/SKILL.md` 的绝对路径取得技能目录，再拼出 `scripts/agents.py` 的绝对路径；例如已持有该路径的 PowerShell 变量 `$leanStackSkillPath` 时，使用 `$leanStackScript = Join-Path (Split-Path -Parent $leanStackSkillPath) 'scripts/agents.py'`，随后以 `py -3 -X utf8 -B $leanStackScript` 调用，不按当前工作目录猜脚本位置。

## 三种对象分开处理

- **live child：**当前会话中的真实运行线程，由 `spawn_agent` 创建、由 `followup_task` 继续；
- **保留身份：**可跨任务重新创建的 `agent_type`、职责、权限和固定配置，由 TOML 与 SQLite 管理；
- **经验记录：**父代理在采用结果后选择保存的去敏经验及完成收据。

保留身份不等于长期存活的线程。`opening_status` 中“存活轮次”是历史开场标签，其数值表示该身份已经记录并采用的成功任务数，不
表示 live child 的线程存活时长或还能否续用。

## 发现与复用

优先使用当前原生工具目录已经显示的 `agent_type`、描述、模型、思考程度和权限。同一能力族按
职责、输入形状、交付、权限、安全风险和证据要求匹配；项目、框架、动作名称、展示名或模型档位
不同不单独创建新身份。

命中已加载保留 `agent_type` 后，为五行开场只对该身份做一次有界 `recall`；目录信息不足，或父代理确实需要经验正文、机器身份和当前 CAS 快照时也定向读取同一身份：

```powershell
py -3 -X utf8 -B .\skills\lean-stack\scripts\agents.py recall --agent-ref <lean_* 机器身份>
```

`recall` 返回的 `agent_ref` 是脚本命令和台账使用的稳定机器身份；`display_name` 只用于用户界面。
`opening_declaration` 的三行与 `opening_status` 的两行构成保留类型首条进展说明的五行开场；前者须与原生目录实际配置核对，并只在实际复用该类型时使名称末尾显示一次 `（复用）`，后两行原样传入任务卡。召回成功后立即派发，子代理读一遍已提供的经验便开始任务；旧经验收据、成本和身份维护均不在此热路径。召回失败时不调用该保留类型，改派最小合规运行时子代理，名称标 `（新建）`，使用“存活轮次：0”“经验：未加载保留经验”开场；不猜测保留计数或经验，也不因状态读取延迟主任务。
不得把中文展示名、任务 `task_name` 或 canonical child path 传给 `--agent-ref`/兼容的 `--name`。

工具目录已经足够时不执行 `status --for-routing`。需要审计受管目录是否遗漏候选时，最多查询一次：

```powershell
py -3 -X utf8 -B .\skills\lean-stack\scripts\agents.py status --for-routing
```

该目录不是 live child 列表，也不证明当前宿主已经热加载刚写入的 TOML。查询失败时立即使用运行时
子代理，不重试、不修库。

## 何时创建或重配身份

只有以下条件同时成立时才 `ensure`：

1. 结果已经核验并被采用；
2. 职责可以去除项目、仓库、路径、网址和一次任务身份；
3. 当前原生目录没有同一能力族、权限和证据边界兼容的身份；
4. 创建或重配不会扩大写权限、安全风险或证据要求。

新能力族已核验具有跨任务价值，且身份、权限可安全绑定时，即便没有新增 `--lesson` 也可按需 `ensure`；保留身份本身无需旧经验、数据库签发收据或 `run_id`，不因此执行 `complete-run`。父代理按 `ensure` 返回的成功或冲突回执决定是否保留，不在调用前自行核验 TOML 文件句柄、锁或台账事务。

需要创建或重配时，`ensure` 的最小可操作输入为：

```powershell
py -3 -X utf8 -B .\skills\lean-stack\scripts\agents.py ensure `
  --role-key <能力族键> --global-domain-key <领域键> `
  --global-contract '{"domain":"...","input_shapes":["..."],"responsibilities":["..."],"deliverables":["..."],"hard_boundaries":["..."]}' `
  --origin-term <当前来源词> --display-name "<中文名>" `
  --description "<可复用职责>" --instructions "<执行边界>" `
  --model <模型> --reasoning-effort <等级> --speed <standard|fast> `
  --authority <read|write>
```

`global_contract` 必须只含示例中的五个字段。`origin-term` 使用当前任务的真实项目、插件或来源词，
只参与去敏拒绝，不写入 TOML、SQLite 或完成收据。配置不同时，只有父代理已经核验并采用新配置，
才把首次响应的 SHA 作为 `--expected-sha256` 对同一请求做一次 CAS 确认。

首次 `ensure` 若返回 `reconfiguration_required` 或 `global_contract_refresh_required`，父代理可以用
响应中的当前 SHA 对同一配置做一次 CAS 确认。锁、结构、身份、文件、权限或 CAS 失败时立即
`auxiliary_skipped`，不排队、不轮询、不重试。写入成功只影响以后新建线程，不能证明旧线程刷新。

保留配置中的 `service_tier` 是宿主预配置；当前 `spawn_agent` 没有逐次速度参数。它不进入模型与
思考程度选择、任务卡或开场声明。

## 按需记录完成与经验

采用结果后，成功结果只有新增一条去敏、带适用范围和证据限制的跨任务经验时才调用 `complete-run`；没有新增经验的成功结果跳过完成记账，但不影响符合上述条件的 `ensure`。已核验并采用的保留身份明确失败可不带 `--lesson` 记录，以维持第二次明确失败删除；运行中、中断、未采用或结果未定均不算失败。临时子代理、普通补问、没有保留身份或无法安全核对身份时直接跳过，不生成收据。

需要记录时才生成一个稳定 UUID `run_id`，用于这次写入及其幂等重放；不要求所有派发预先生成
UUID。只有需要声称某版旧经验参与该次并发完成结果时，才在派发前用同一个 `run_id` 取得数据库签发收据：

```powershell
py -3 -X utf8 -B .\skills\lean-stack\scripts\agents.py recall `
  --agent-ref <lean_* 机器身份> --expected-sha256 <CAS 快照> --run-id <UUID>
```

需要关联旧经验时保存返回的 `agent_ref`、`sha256`、`experience_digest` 和 `experience_receipt`。下例只用于已有新增经验的成功结果：

```powershell
py -3 -X utf8 -B .\skills\lean-stack\scripts\agents.py complete-run `
  --agent-ref <lean_* 机器身份> `
  --expected-sha256 <调用方保存的 CAS 快照> `
  --run-id <UUID> `
  --invocation-kind spawn_agent `
  --outcome success `
  --origin-term <用于去敏检查的来源词> `
  --lesson "适用范围：<可跨任务复用的情境>；证据限制：<已核验依据与未覆盖边界>"
```

只有真实使用了某版经验并需要保留这项关联证据时，才同时附摘要和收据；两项必须成对出现，
当前摘要也不能省略收据。`recall --run-id` 会用一个短 SQLite 事务，把当时由数据库和受管 TOML
共同证明的摘要、机器身份和 `run_id` 绑定到随机收据；普通不带 `run_id` 的召回仍为只读。同一
绑定重复召回返回原收据，其他运行、后补、从 owner token 计算、历史曾出现或跨身份的摘要都不
构成签发证据。该关联只证明脚本签发过该版本，不证明宿主一定加载了经验，也不证明经验导致成败。

调用时确实使用旧经验并需关联该版本时，在上述 `--lesson` 前成对附上：

```powershell
  --loaded-experience-digest <调用时摘要> `
  --experience-receipt <同一 run_id 的数据库签发收据> `
```

`--lesson` 须写明适用范围和证据限制；失败教训只保留情境、停止依据和重开条件，不把尚未明确的结果当失败，也不把失败教训作为失败记录的 `--lesson` 参数。经验不得包含项目名、仓库、路径、网址、日志、凭据、原始提示、源码、固定文件清单或模型思维
过程。明确失败可用 `--outcome failure` 且不附 `--lesson`，只在身份及 CAS 可安全核对时执行 `complete-run`。用户否定的结果不得采用或写入；若已经误写，只追加一条具名纠正
事件并让受污染摘要失效，不能伪称物理删除历史事件。

`record-run` 和独立 `improve` 只保留兼容与专门维护用途：普通新结果统一使用 `complete-run`；
`improve` 仅用于后来纠正或确有必要的摘要压缩。健康结构下新增经验直接按需保存，不等待历史
摘要纠错、压缩或单独版本巡检；脚本若报告结构不合规，就安全跳过本次写入，父代理保留原已
核验结果和具体失败回执，后续备份、显式修复，再核验是否成功保存。摘要维护只在能与真实
工作并行且不争用时按需执行，不能阻塞主任务或新经验保留。

## 现实旧状态迁移

普通命令不猜测旧台账。精确 v1/v2/v3 只通过 `migrate-global --plan <UTF-8 JSON>` 迁移；计划根
对象必须只有 `format_version: 1` 和 `roles`，并覆盖每个旧身份一次。每个 `roles` 项必须完整给出：

```json
{
  "old_name": "...", "old_role_key": "...", "expected_sha256": "...",
  "new_role_key": "...", "display_name": "...", "description": "...",
  "instructions": "...", "global_domain_key": "...",
  "global_contract": {
    "domain": "...", "input_shapes": ["..."], "responsibilities": ["..."],
    "deliverables": ["..."], "hard_boundaries": ["..."]
  },
  "origin_terms": ["..."],
  "experience_corrections": [{"event_id": "<被纠正事件 UUID>", "lesson": "<纠正>"}]
}
```

不需要纠正时使用空数组。精确 v4/v5/v6/v7 只运行 `migrate-attempts` 升到 v8。迁移必须保留身份、所有权、
创建时间、运行记录和原始经验；新建的召回签发表为空，不为历史运行补造签发。旧运行的失败、
经验复用和完成收据仍保持 unknown。任一结构、身份、哈希、目标冲突或文件操作失败时零写入或
按原字节恢复，不自动合并、不猜职责。

## 数据完整性边界

以下保护由 `agents.py` 执行并以成功、冲突或跳过回执判定，不能因流程精简而弱化；父代理无需在复用或新身份 `ensure` 前逐项预检文件句柄、锁和事务：

- 机器身份、受管目录、普通文件、单硬链接、owner token 和路径边界检查；
- 首次写入使用调用方保存的精确 SHA-256 做 CAS；
- 经验版本关联必须命中同一身份、同一 `run_id`、同一摘要和随机收据的数据库签发记录；
- 同一 `run_id` 的重放核对身份、调用类型、结果、经验版本、完成收据和经验事件；
- SQLite 事务串行化使用同一台账的写者；TOML 更新按原字节核验，异常时尝试恢复，恢复不完整须显式报错并保留现场。Windows 上已覆盖的受管 TOML 重配、删除和跨名称迁移从最终核验到文件操作持有目标对象及父目录句柄；归档目录整体搬移仍是路径级保护，POSIX 仍依赖合作写者。SQLite 与文件系统不是共同原子事务，进程崩溃后的跨存储恢复仍有缺口；
- 旧迁移行没有完成或召回签发收据时保持 unknown，不能依据相同正文或碰撞 event 猜测关联；
- 运行中、中断、未采用、用户停止、工具阻断或结果未定不记录为失败；
- 同一身份累计第二次明确失败时，按当前数据保护规则永久移除身份和关联记录。

完整迁移、纠正、摘要和精确删除参数由脚本 `--help` 与行为测试承载，不复制到普通派发说明。
永久删除只在既有第二次明确失败规则，或用户明确要求且满足零记录、精确 owner token 与 SHA
校验时执行。

## 用户可见回执

只有实际执行了持久化操作时才简短报告：

- 复用、创建、重配或跳过了哪个 `display_name`；
- 完成结果和经验是否记录；
- 若写入失败，记录具名未完成事项、决定性原因和下一次安全修复条件；父代理在主任务推进后
  修复并回读验收，不能只报告原因或把未保存写成已保存。

不向用户展示 owner token、完整经验正文、内部路径、长 SHA 清单或完整数据库状态。没有进入本
分支时不生成“未保存”收尾报告。
