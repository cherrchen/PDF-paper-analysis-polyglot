# Agent Note 规则

[中文](./AGENTS.md) | [English](./AGENTS.en.md)

## 先检索

判定变更是事实更新、部分取代、完全取代，还是新决策。

## 事实更新

路径或默认值变了，决策仍成立：更新已落地 note。

## 决策变更

写新 note。不要把旧决策改写成其反面。

## 部分取代

两边都保持现行，并交叉链接。

## 完全取代

保留独特理由，然后归档旧的已落地 note。

## 提案格式

以 `# Agent Note:` 开头，并写 `Status: proposed`。英文伴侣必填：Problem、Proposal、Alternatives considered、Acceptance criteria、Risks。中文主文件使用对应中文标题。

## 已落地格式

`Status: implemented`。英文伴侣必填：Problem、Decision、Alternatives considered、Consequences。不要留下提案期小节。中文主文件使用对应中文标题。

两个文件都保留语言跳转。见 [`docs/development/bilingual.md`](../../docs/development/bilingual.md)。

## 否决

`Status: rejected — <一行原因>`。保留提案作为已考虑方案。删除低价值的否决 note。

## 归档

只有已落地 note 可以归档。冻结。不再是当前权威。
