# 文档

当前 `main` 的默认在线入口是 Everweave 自己的 ChatGPT 设备 OAuth，使用 GPT-5.6 Luna / high 和 Responses SSE。下列标为阶段记录的文档保留旧版本的实验数字与问题，不应当覆盖当前代码事实。

## 使用与开发

- [使用指南](LOCAL_SETUP.md) 包含安装、模型连接和独立存档
- [Codex 订阅接入](CODEX_SUBSCRIPTION.md) 说明 Luna / high、登录边界和本轮实测
- [语言设置](LOCALIZATION.md) 说明中英文界面与生成语言
- [示例世界](SHOWCASE.md) 记录 README 中章节系统加入前的场景与截图
- [开发与测试](DEVELOPMENT.md) 说明资源准备和回归方法
- [架构](ARCHITECTURE.md) 介绍客户端、本机服务与生成调度
- [内容协议](EXECUTABLE_CONTENT.md) 说明场景、规则和可执行效果
- [章节与游戏规格](CAMPAIGNS.md) 说明规划、共享线索、连接图和可选资源系统
- [冒险导演](ADVENTURE_DIRECTOR.md) 说明持续复盘、人物、跨区技能、任务与内容委托
- [快速自主试玩](FAST_PLAYTEST.md) 说明意图操作、事件中断和玩家视野边界
- [生成节奏、任务披露与敌人行为](PACING_AND_ENCOUNTERS.md) 记录当前迭代、实测结果和未完成范围
- [冒险导演交付记录](ADVENTURE_VALIDATION.md) 区分真实模型生成、自主操作与固定回归
- [章节系统交付记录](CAMPAIGN_VALIDATION.md) 区分代码检查、模型联调、原始响应回放和待完成试玩
- [混合内容库](HYBRID_CONTENT.md) 说明素材引用、音频、材质和扩库
- [日志](LOGGING.md) 与 [安全边界](SECURITY.md)

## 专项设计与实验记录

下列文档记录各阶段的实现和测试结果。旧版本的数字、截图和限制不代表当前版本。

- [蓝图场景与地表](SCENE_QUALITY.md)
- [旅图、初始物品与手记](JOURNEY_AND_POSSESSIONS.md)
- [预生成调度](PREFETCH_RELIABILITY.md)
- [协议容错](PROTOCOL_RELIABILITY.md)
- [混合内容验证](HYBRID_VALIDATION.md)
- [前端布局](FRONTEND_PREVIEW.md)
- [Content Runtime v2 验证](REFRACTOR_TEST_REPORT.md)
- [早期引擎验证](ENGINE_REVIEW.md) 与 [早期生成图形](VISUALS_AND_PREFETCH.md)
