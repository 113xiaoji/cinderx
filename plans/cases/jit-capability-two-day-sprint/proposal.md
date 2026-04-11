# Proposal

## Case

`jit-capability-two-day-sprint`

## Objective

在两天内，不追求“补齐所有顶级 JIT 能力”，而是优先交付能显著提升：

- 性能迭代速度
- 稳定性
- profitability 决策质量
- 后续能力演进的基础设施

## Reality check

两天内不现实的目标：

- 完整的多层级 tiering
- 广覆盖 OSR
- 完整 escape analysis / scalar replacement 体系
- 成熟的 profile-guided 全闭环

两天内现实且高 ROI 的目标：

- 把验证/benchmark 基础设施拉到“能高频稳定复现、低人工干预”
- 把 current profitability policy 从 ad-hoc 调阈值推进到更可观测、更可扩展的一层
- 针对 1-2 个高价值热点形状落真正的性能/稳定性改进
- 为后续 tiering / feedback / object-model work 铺好接口和数据面

## Success criteria

- 远端 ARM 验证入口统一并稳定
- 至少一组关键 benchmark / probe 的回归定位时间显著下降
- profitability 决策不再只依赖硬编码阈值，而有更清晰的数据支撑
- 至少一个高价值热点形状拿到可复现的收益或稳定性改善
