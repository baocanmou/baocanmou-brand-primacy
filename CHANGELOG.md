# 更新记录

## 0.2.0（2026-10-05）

支持国产 AI 工具。

- 新增 `PROMPT.md` 聊天版：DeepSeek、Kimi、豆包、通义千问、文心等不能加载 Skill 的聊天窗口，复制全文即可使用，计分改为手算。由 `scripts/build_prompt.py` 从 SKILL.md 生成。
- README 补充 Kimi Code CLI、文心快码、Qwen Code、TRAE、豆包、扣子的安装方法。
- 发布页附 Skill 压缩包，供豆包、扣子上传。
- SKILL.md 说明脚本路径相对于技能目录，方便在其他工具里运行。

## 0.1.0（2026-10-01）

首个版本。

- 三种模式：完整策略、决策校验、复测。
- CUMS 评分细则：16 个检查项，统一的六级证据阶梯，证据类型封顶。
- `scripts/score.py`：维度得分、几何平均、档位、补短板顺序、源力句状态与证据规则检查。
- `scripts/jev_review.py`：可选，用 TypeSafe Jev 对打分、源力句和行动做第二意见复核。
- 两个虚构示例：穗禾烘焙（中）、轻气轻食（弱，源力未成立）。
