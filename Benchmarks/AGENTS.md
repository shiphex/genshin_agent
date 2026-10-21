# Benchmark开发指引

先读[分类索引](README.md)与[当前状态](context.md)，再读所属分类说明。根项目约定继续适用，Python环境由项目根uv统一管理。

- 按被测任务建立分类，不照搬生产包结构；场景、oracle和专用辅助留在所属目录。
- `support/`面向当前及未来所有Benchmark。至少两个分类确实需要相同行为时才提取；共享代码不导入分类实现，由根入口组合跨分类结果。
- 各分类维护自己的命令、指标和限制；顶层只维护导航、通用约束及薄入口。新增文档同步根预算与入链。
- 固定输入、记录原始数据和明确分母；执行完成、引用合法、语义正确及用户验收分开报告。有限回放只验证框架。
- 代码、测试和场景跟踪Git；回答、评审和报告写入`outputs/`独立新目录，失败也保留。迁移前的历史输出原位只读，不重写manifest或绑定，不自动清理。
- 普通开发使用离线合成测试；真实模型请求需任务授权，不自动启动或下载服务。RAG实现、题库、catalog和冻结快照只读复用。
- 子进程测试用独立临时目录，确认worker、后代和IO线程结束；性能计时与内存采样分开。交付运行所属测试与项目doc-sync，不自动提交、推送或上传。

组织方式参考[上游目录指引](https://github.com/deepseek-ai/deepseek-harness/blob/master/benchmarks/AGENTS.md)；[内存限制说明](https://github.com/deepseek-ai/deepseek-harness/blob/master/.agents/notes/implemented/testing/2026-10-07-memory-limited-benchmarks.md)仅作为运行条件的分类参考，本项目尚未实现内存受限运行。
