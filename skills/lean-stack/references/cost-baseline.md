# 成本预估

本文件是维护参考，不是每次主任务重新计算的运行时强制规则。只有 OpenAI 官方模型或费率
发生变化，或用户明确更改成本策略时才更新；没有变化时保持不动。普通主任务直接使用固定预估，维护检查
不是主任务前置条件。

## 当前基线

核对日期：Astra 为 2026-09-24，Terra 为 2026-10-27；Sol 尚未核验。来源为文末官方页面；以下为 API 美元价格，不把单价比例当作整项任务节省，也不推断 Codex credits 结算。

### API 美元基线

OpenAI 官方页面在各自核对日期的标准处理、短上下文每百万令牌价格（缓存写入为 30 分钟保留）：

| 模型 | 输入 | 缓存输入 | 缓存写入 | 输出 |
| --- | ---: | ---: | ---: | ---: |
| gpt-6-astra | $10 | $1 | $12.50 | $50 |
| gpt-6.1-sol | 待官方核验 | 待官方核验 | 待官方核验 | 待官方核验 |
| gpt-6.1-terra | $1.00 | $0.05 | $1.25 | $5.00 |

2026-09-30 按用户要求统一 Sol 为 `gpt-6.1-sol`；其费率尚未核验，不沿用旧 Sol 的价格。
2026-10-27 按用户要求用 Terra 取代 Luna 的速度优先路线；Terra 的单价独立核对，不沿用 Luna 的价格，也不声称比 Luna 更便宜或已实测更快。
已有数字仍是各自核对日期的基线。各模型四列价格分别以表中数字为准；不同列的模型间比例不一定相同。不据此猜测当前任务计费类别、token 用量或账户实际结算。

### 选模时使用这份价格

三模型的选择规则由[模型与思考程度](dispatch-start.md#模型与思考程度)承载；
复制和变体的触发由[任务类型组、复制与变体](agent-groups.md)承载。
本表只给相同计费档位、上下文类别和令牌形状下的 API 单价参照。实际子任务先守住必要质量，
可靠性相当时比较总成本；成本可接受时可为缩短父任务时间增加调用，并联合选择模型与思考程度。
台账复用可减少角色提示重建和重复交接，在可靠性相当时优先；但注入经验与新启动一个子代理仍有成本，
实际收益按当前增量输入判断。复用条件只列当前会话已经加载、属于同一能力族、质量兼容；全局权限、
安全、数据完整性和诚实证据规则照常执行，不重复作为复用概率门槛。
当前子代理与台账保留子代理都可用时，质量达到要求后比较父子合计总成本，选择更低成本的一条，
不为统计台账复用强制换线程。只有任务类型、质量门槛、权限或证据边界、专家必要性、预计成本发生
实质变化时才重新选路；同一任务的语义增量沿用入口快判，新增确定性计算由父工具处理；
不重复论证必要性或评估模型，也不逐调用查询价格。日常成本比较用已有信息粗判，不要求算出
每条路线的令牌、价格或耗时；只有可能改变当前选择的显著成本疑问才定向补查，不阻塞其他就绪切片。
Astra 只在最强可行 `gpt-6.1-sol` 仍有决定性质量缺口时使用；当前可用模型、思考档和保留类型配置以
运行环境和派发规则为准。单价、调用数量及工具输出的估计令牌数都不能证明实际账户结算或
某次任务的成本节约；普通调用无需重算令牌或查询成本状态。

## 独立成本维护

普通子代理调用、复用、读取保留子代理、`ensure` 和 `complete-run` 不触发成本状态查询。
只有明确启动独立维护动作且不阻塞主任务时，才运行本地 `scripts/cost_check.py status`；
该脚本不联网、不改插件文件，仅在 `<CODEX_HOME>/lean-stack/cost-check-v1.json`
记录核对时间；无需自动化、定时任务、守护进程或专门子代理。

```text
py -3 -X utf8 <插件技能目录>/scripts/cost_check.py status
```

返回 `fixed_baseline_current`（七天未到）即结束；返回 `official_check_due` 且官方核对可与主任务并行时，
只核对下列 OpenAI 官方来源。页面不可确认或检查失败就保持到期并结束维护；事实不变时保持
本文件，事实变化时先更新本文件。两种确认完成的情况都执行一次 `record`：

```text
py -3 -X utf8 <插件技能目录>/scripts/cost_check.py record --expected-state-sha256 <status 返回的当前状态哈希>
```

首次没有状态文件时省略 `--expected-state-sha256`；已有状态必须提供最新哈希，冲突、异常或
并发占用时安全跳过，不覆盖较新的结果，也不拖延主任务。旧版合法状态由脚本兼容读取，
合法记录时归一；状态文件或锁载体无需手工清理。锁的原子写入、安全路径和竞争处理由脚本实现。

## 官方来源

- [GPT-6.1 Terra 模型说明与价格](https://developers.openai.com/api/docs/models/gpt-6.1-terra)
- [模型选择与 Terra 适用任务](https://developers.openai.com/api/docs/guides/model-selection)
- [OpenAI API 价格](https://developers.openai.com/api/docs/pricing)
- [OpenAI Codex 费率](https://learn.chatgpt.com/docs/pricing)
- [OpenAI Codex 子代理](https://learn.chatgpt.com/docs/agent-configuration/subagents?surface=app)
- [OpenAI 模型比较](https://developers.openai.com/api/docs/models/compare)
- [GPT-6 Astra 行为与提示指导](https://developers.openai.com/api/docs/guides/latest-model?model=gpt-6-astra)
