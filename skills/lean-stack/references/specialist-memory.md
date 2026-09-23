# 保留子代理身份与经验

选中已加载保留类型时，仅对该身份定向召回；结果已核验、已采用且确有跨任务价值时才维护
保留身份或经验。普通 `spawn_agent`、同任务 `followup_task` 和临时角色不触发写入；身份维护
不能成为派发前置，也不能延迟主任务动作或交付。普通派发无需成本、迁移或摘要巡检。[agents.py](../scripts/agents.py) 只管理受管
TOML 与 SQLite，不启动子代理，亦不能证明宿主加载了身份或经验。

下列相对脚本路径示例只适用于本插件源码仓库根。跨项目调用时，从当前已加载的
`lean-stack/SKILL.md` 的绝对路径取得技能目录：`$leanStackScript = Join-Path (Split-Path -Parent $leanStackSkillPath) 'scripts/agents.py'`，
再以 `py -3 -X utf8 -B $leanStackScript` 调用，不按当前工作目录猜路径。

## 定向召回

live child 是当前会话的线程；保留 `agent_type` 是跨任务身份；经验是结果采用后的可选记录。
优先按原生工具目录中职责、输入、交付、权限、安全风险及证据要求匹配同能力族。
工具目录足够时不执行 `status --for-routing`；确需审计遗漏候选时最多查一次，失败就使用
运行时子代理。

命中已加载类型后，只对该身份做一次有界 `recall`：

```powershell
py -3 -X utf8 -B .\skills\lean-stack\scripts\agents.py recall --agent-ref <lean_* 机器身份>
```

`agent_ref` 是稳定机器身份，`display_name` 只用于用户界面；不得把中文展示名或子线程
路径传给 `--agent-ref`。`opening_declaration` 三行须与原生目录实际配置核对，
`opening_status` 两行原样进入[五行任务卡](dispatch-start.md#任务卡上下文与所有权)。
其中“存活轮次”是该身份已记录并采用的成功任务数，不是 live child 的线程寿命。
召回成功后立即派发；受管 TOML 的 `developer_instructions` 已包含经验，任务卡只传五行
状态，不再复制经验正文，子代理读原生注入经验一次即开工。旧经验与当前技能冲突时按当前技能。
召回失败时改派最小合规运行时子代理，名称标 `（新建）`，使用“存活轮次：0”和
“经验：未加载保留经验”，不猜测状态、不重试或修库。

## 创建或重配身份

结果已有可复用能力族、已核验并采用，且职责可去除来源身份时：

- **新建：**原生目录无同能力族、权限及证据边界兼容的身份；仅在已有证据提示存在未加载
  身份时定向核查受管台账。确认没有兼容身份后，才 `ensure` 一个最小权限身份；项目名、
  框架或模型档位不同不另建。
- **重配：**已有同身份且能力族、权限、证据边界兼容，但固定配置需要更新时，先核验并采用
  配置胜者，再以该身份当前可用 SHA 执行 `--expected-sha256` CAS；权限不扩大。
  当前宿主已加载的旧配置不会热刷新，新任务才可验证新配置。

新身份即便没有新增 `--lesson` 也可按需 `ensure`。保留身份本身无需旧经验、数据库签发
收据或 `run_id`，不因此执行 `complete-run`。`ensure` 不依赖旧经验、收据或完成记账。
命令最小输入如下，`global_contract` 只含示例五字段：

```powershell
py -3 -X utf8 -B .\skills\lean-stack\scripts\agents.py ensure `
  --role-key <能力族键> --global-domain-key <领域键> `
  --global-contract '{"domain":"...","input_shapes":["..."],"responsibilities":["..."],"deliverables":["..."],"hard_boundaries":["..."]}' `
  --origin-term <当前来源词> --display-name "<中文名>" `
  --description "<可复用职责>" --instructions "<执行边界>" `
  --model <模型> --reasoning-effort <等级> --speed <standard|fast> `
  --authority <read|write>
```

`origin-term` 仅供去敏拒绝，不进入受管存储。首次 `ensure` 返回
`reconfiguration_required` 或 `global_contract_refresh_required` 时，只有已核验并采用
该配置且响应给出当前可用 SHA，才对同一身份、同一请求做一次 CAS 确认；若已有竞争变更，
重新判断胜者，不拿旧 SHA 强写。父代理按 `ensure` 返回的成功或冲突回执决定是否保留；
锁、结构、身份、权限或 CAS 失败时 `auxiliary_skipped`，不轮询、不让身份维护阻塞主线。
`service_tier` 是宿主预配置，不进入逐次派发任务卡。

## 按需记录完成与经验

采用的成功结果只有新增一条去敏、带适用范围和证据限制的跨任务经验时才调用
`complete-run`；无新增经验的成功结果跳过完成记账，但不影响符合上述条件的 `ensure`。
已核验并采用的保留身份发生明确失败时，可用 `--outcome failure` 且不附 `--lesson` 记账，以维持累计
第二次明确失败删除；运行中、中断、未采用或结果未定均不算失败。临时角色或身份与 CAS
无法安全核对时跳过写入。

需要记录时才生成稳定 UUID `run_id`。只有需要声称某版旧经验参与该次并发完成结果时，
派发前用同一 `run_id` 定向 `recall --agent-ref <lean_*> --expected-sha256 <SHA> --run-id <UUID>`
取得数据库签发的 `experience_digest`、`experience_receipt`，并在完成调用中成对传入
`--loaded-experience-digest` 与 `--experience-receipt`。普通召回只读；收据只证明该版本
曾对同一机器身份和 `run_id` 签发，不证明宿主加载或经验导致结果。不得依据相同正文或历史
摘要猜测关联。

```powershell
py -3 -X utf8 -B .\skills\lean-stack\scripts\agents.py complete-run `
  --agent-ref <lean_* 机器身份> --expected-sha256 <调用方 CAS 快照> `
  --run-id <UUID> --invocation-kind spawn_agent --outcome success `
  --origin-term <用于去敏检查的来源词> `
  --lesson "适用范围：<可复用情境>；证据限制：<已核验依据与未覆盖边界>"
```

经验不含项目名、路径、URL、日志、凭据、原始提示、源码或思维过程。失败教训只写
“情境、停止依据、重开条件”，不作为失败记录的 `--lesson`。用户否定已写结果时只追加
具名纠正事件并使受污染摘要失效；完整纠正、压缩及兼容命令见脚本 `--help` 和行为测试。
健康结构下新增经验直接按需保存，不等待历史摘要纠错；结构不合规时安全跳过，保留已核验
结果和失败回执，后续备份、显式修复并回读验收。

## 旧状态与数据保护

精确 v1/v2/v3 只经 `migrate-global --plan <UTF-8 JSON>` 迁移；计划必须用
`format_version: 1` 覆盖每个旧身份一次，逐项提供身份、旧/新角色键、当前 SHA、描述、
指令、五字段 `global_contract`、`origin_terms` 和 `experience_corrections`（无纠正用空数组）。
精确 v4/v5/v6/v7 只用 `migrate-attempts` 升到 v8。迁移保留原身份、所有权、原始经验和
运行记录；旧运行、召回及经验版本关联保持 unknown，不回填签发。结构或哈希不符须零写入
或按原字节恢复；完整计划格式与验证见脚本 `--help` 和迁移行为测试。

安全规则由 `agents.py` 执行并以成功、冲突或跳过回执判定：机器身份、受管目录、普通
文件、单硬链接、owner token、路径边界；精确 SHA-256/CAS；同一 `run_id`、同一摘要与
随机收据的数据库签发；幂等重放；SQLite 事务串行化使用同一台账的写者；TOML 原字节核验，
恢复不完整须显式报错。Windows 上已覆盖的受管 TOML 重配、删除和跨名称迁移持有目标对象与
父目录句柄；归档目录整体搬移仍是路径级保护，POSIX 仍依赖合作写者。SQLite 与文件系统
不是共同原子事务，进程崩溃后的跨存储恢复仍有缺口。永久删除限于累计第二次明确失败，
或用户明确要求并满足零记录、owner token 和 SHA 校验；不留退役副本。

## 用户可见回执

只在实际持久化后简短报告身份创建、复用、重配或跳过，及结果/经验是否记录。
失败写入保留具名未完成事项、决定性原因和安全修复条件，主线推进后修复并回读；
不展示 owner token、经验正文、内部路径或 SHA 清单。未进入本分支不生成保留报告。
