"""把 SKILL.md 和它引用的参考文件合并成一份聊天版提示词 PROMPT.md。

给不能加载 Skill 的聊天窗口用：DeepSeek、Kimi、豆包、通义千问、文心等。
改了 SKILL.md 或参考文件后重新运行；加 --check 只检查 PROMPT.md 是否需要重新生成。
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TITLE = '包参谋·品牌源力策略（聊天版）'
CHAT_RULES = """\
你现在按下面的“包参谋·品牌源力策略”方法工作。你在聊天窗口里，不能运行脚本，也不能读写文件，所以：

- 第 5 节“计算与复核”：不写 JSON，不运行脚本，按附录《报告格式》里的计算规则手算，报告里注明“手算”。跳过 Jev 复核，在报告末尾注明“未做 Jev 复核”。
- 文中提到的参考文件都附在本文后面，按附录标题查找。
- 用户还没讲品牌情况时，先请对方介绍生意、顾客和对手，不要先交付空报告。"""

USAGE = ('> 用法：复制本文件全文，作为第一条消息发给 AI（DeepSeek、Kimi、豆包、通义千问、文心等），'
         '或作为附件上传后说“按这个文件做”，再讲你的情况。\n'
         '> 本文件由 `scripts/build_prompt.py` 从 SKILL.md 生成，要改请改源文件后重新生成。')

LINK = re.compile(r' ?\[([^\]]+)\]\((references/[^)#\s]+\.md)\) ?')


def build():
    skill = (ROOT / 'SKILL.md').read_text(encoding='utf-8')
    body = re.sub(r'\A---\n.*?\n---\n', '', skill, flags=re.S).strip()
    refs = {}
    for text, path in LINK.findall(body):
        refs.setdefault(path, text)

    def cite(match):
        path = match.group(2)
        return f'附录《{refs[path]}》' if path in refs else match.group(1)

    parts = [f'# {TITLE}', USAGE, CHAT_RULES, '---', LINK.sub(cite, body)]
    for path, text in refs.items():
        ref = (ROOT / path).read_text(encoding='utf-8').strip()
        ref = re.sub(r'\A# .*\n+', '', ref)
        parts += ['---', f'# 附录《{text}》', LINK.sub(cite, ref)]
    return '\n\n'.join(parts) + '\n'


def main():
    out = ROOT / 'PROMPT.md'
    text = build()
    if '--check' in sys.argv:
        if not out.exists() or out.read_text(encoding='utf-8') != text:
            print('PROMPT.md 已过期，请运行 python3 scripts/build_prompt.py')
            return 1
        print('PROMPT.md 是最新的')
        return 0
    out.write_text(text, encoding='utf-8')
    print(f'已生成 {out.name}，{len(text)} 字符')
    return 0


if __name__ == '__main__':
    sys.exit(main())
