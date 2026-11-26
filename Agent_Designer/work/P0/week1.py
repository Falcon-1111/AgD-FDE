import io
import re
import pandas as pd

# 定义文件路径（换成你本机真实的 CSV 路径）
file_path = '/Users/falcon/trainer/data/sample_financials.csv'

# 显式 schema：写死预期的 8 个列名（含顺序），与表头自身无关。
EXPECTED_COLUMNS = [
    '股票代码',
    '公司简称',
    '报告期',
    '营业收入_亿元',
    '归母净利润_亿元',
    'roe_pct',
    '资产负债率_pct',
    '行业',
]


def _schema_diff_reason(actual_cols, expected_cols):
    """给出"实际列名 vs 预期列名"的可定位诊断串（不含 raise）。"""
    exp = list(expected_cols)
    act = list(actual_cols)
    missing = [c for c in exp if c not in act]
    extra   = [c for c in act if c not in exp]
    if not missing and not extra:
        return '列名集合一致但顺序不同'
    reason = '列名集合不一致'
    if missing:
        reason += f'；缺少 {missing}'
    if extra:
        reason += f'；多出 {extra}'
    return reason


def assert_expected_header(header_cols, expected_cols=EXPECTED_COLUMNS):
    header = list(header_cols)
    if header == list(expected_cols):
        return header
    reason = _schema_diff_reason(header, expected_cols)
    raise ValueError(
        'schema 校验失败（前置：读文件后、千分位回拼前，直接针对表头）：'
        f'表头与 EXPECTED_COLUMNS 不一致（{reason}）。\n'
        f'  预期({len(expected_cols)}列): {list(expected_cols)}\n'
        f'  实际表头({len(header)}列): {header}'
    )


def _is_number(s):
    """是否是一个合法数字字面量（用于判断合并后是否仍为数值）。"""
    s = s.strip()
    if s == '':
        return False
    try:
        float(s)
        return True
    except ValueError:
        return False


def _int_digit_len(s):
    """返回一个数字字面量"整数部分"的位数；无法解析时返回 None。"""
    m = re.match(r'^[+-]?(\d+)', s)
    return len(m.group(1)) if m else None


# 千分位组的严格形态：恰好 3 位整数，可带小数，如 845.60 / 002 / 100.50。
# 注意：这里刻意收紧——只有"恰好 3 位整数"的右段才可能是被千分位逗号切出来的残段。
_THOUSANDS_GROUP = re.compile(r'^\d{3}(?:\.\d+)?$')


def read_thousand_sep_csv(path, encoding='utf-8-sig'):
    with open(path, 'r', encoding=encoding, newline='') as f:
        lines = [ln for ln in f.read().splitlines() if ln.strip()]

    # —— A. 前置 schema 校验（赶在千分位回拼之前）——
    header_cols = lines[0].split(',')
    assert_expected_header(header_cols)   # 不等直接 raise ValueError，指到表头

    ncols = len(header_cols)   # 已通过前置校验，必然 == len(EXPECTED_COLUMNS)

    fixed = [lines[0]]
    for line in lines[1:]:
        parts = line.split(',')

        # —— C. 本就对齐的行：原样保留，绝不误合并 ——
        if len(parts) == ncols:
            fixed.append(line)
            continue

        # 数据行比表头还少列：回拼只会减少段数、补不回来，无法用千分位解释 -> 明确报错
        if len(parts) < ncols:
            raise ValueError(
                f'列数不齐（数据行比表头少列：期望{ncols}，实得{len(parts)}），'
                f'无法用千分位解释，拒绝猜测：{line}'
            )

        # 段数多于表头：只允许按"严格千分位"规则逐段回拼
        fields = []
        i = 0
        n = len(parts)
        while i < n:
            cur = parts[i]
            first_merge = True          # cur 是否仍是该数值最高位那一组的残段
            while i + 1 < n:
                nxt = parts[i + 1]
                # 右段必须是"恰好 3 位整数(可带小数)"的千分位组
                if not _THOUSANDS_GROUP.match(nxt):
                    break
                # 千分位只切整数部分，左段必须数字结尾
                if not re.search(r'\d$', cur):
                    break
                merged = cur + nxt
                if not _is_number(merged):
                    break
                # 首次合并：cur 是被切数的最高位残段，必须是 1~3 位整数且不含小数点；
                # 否则 cur 本身已是完整独立数值（如 2023 / 845.60），不该被当成千分位残段。
                if first_merge:
                    ilen = _int_digit_len(cur)
                    if ilen is None or not (1 <= ilen <= 3) or ('.' in cur):
                        break
                cur = merged
                first_merge = False
                i += 1
            fields.append(cur)
            i += 1

        # —— 猜不出来就明确报错，不再硬凑 ncols ——
        if len(fields) != ncols:
            raise ValueError(
                f'无法用千分位规则唯一还原（期望{ncols}列，实得{len(fields)}列）：'
                f'该行含非千分位的多余/缺失列，拒绝猜测——{line}'
            )
        fixed.append(','.join(fields))

    return pd.read_csv(io.StringIO('\n'.join(fixed)))


def validate_schema(df, expected_cols=EXPECTED_COLUMNS):
    actual_cols = df.columns.tolist()
    if actual_cols == list(expected_cols):
        return actual_cols
    reason = _schema_diff_reason(actual_cols, expected_cols)
    raise ValueError(
        f'schema 校验失败（下游兜底）：实际列名与 EXPECTED_COLUMNS 不一致（{reason}）。\n'
        f'  预期({len(expected_cols)}列): {list(expected_cols)}\n'
        f'  实际({len(actual_cols)}列): {actual_cols}'
    )


try:
    df = read_thousand_sep_csv(file_path)

    # 表头级校验已在 read 内前置完成；这里再做一次下游兜底。
    validate_schema(df)

    print(f'CSV 文件总行数: {len(df)}')
    print('列名:', df.columns.tolist())
    print('\n前 5 行数据概览:')
    print(df.head())

    # 数值列确认为 float（错列时它们会变成 object/错位）
    num_cols = ['营业收入_亿元', '归母净利润_亿元', 'roe_pct', '资产负债率_pct']
    print('\n数值列类型:')
    print(df[num_cols].dtypes)

except FileNotFoundError:
    print(f'错误: 找不到文件 {file_path}，请检查路径是否正确。')

#三个问答：
#1、如果 CSV 少一列，脚本会怎样报错？
# 答：
# 场景 A：整个文件的所有行都少了一列（表头和数据行一致），结果：表头被改/少列时，read_thousand_sep_csv 内的前置 assert_expected_header 会在回拼之前就 raise ValueError（诊断"缺少 [...]"），直接指向表头。
# 场景 B：只有部分数据行多了一列（表头有 8 列，但某行切出 9 段），带千分位回拼的脚本里，回拼会把多出来的段当成千分位贪心合并。只要凑得回 ncols 列就一路放行、静默产出列名/数值错位的脏表（实测营业收入列被错填），凑不回才抛"列数不齐"。修复后回拼只认严格千分位形态（高段必须 1~3 位整数），对这类多列一律"猜不出即报错"。
# 场景 C：只有部分数据行少了一列（表头有 8 列，但某行切出 7 段），回拼只会减少段数、补不出缺的列，数据行进入回拼分支后段数仍 < 表头列数，当前脚本会在把数据交给 pandas 之前 raise"列数不齐（少列）"。本脚本的回拼分支会先一步抛错。
# 2、如果文件路径带中文和空格，还能跑吗？
# 答：可以正常运行。
# 3、你打印出来的"行数"，包含表头吗？
# 答：不包含，表头是列名。
#我对源文件前3行的数字，核了"营业收入_亿元、归母净利润_亿元、roe_pct、资产负债率_pct"四列的数值，发现它们与源文件完全一致，说明脚本正确处理了千分位逗号问题。
