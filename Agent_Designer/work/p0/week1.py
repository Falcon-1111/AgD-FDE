import io
import re
import pandas as pd

# 定义文件路径（换成你本机真实的 CSV 路径）
file_path = '/Users/falcon/trainer/data/sample_financials.csv'


def read_thousand_sep_csv(path, encoding='utf-8-sig'):
    """读取“未加引号但字段内含千分位逗号”的 CSV，解决错列问题。

    两个坑：
    1) UTF-8 BOM：用 encoding='utf-8-sig' 吃掉，否则首列名会变成 '股票代码'。
    2) 千分位逗号（如 2,845.60）没加引号，被当成列分隔符 → 整行右移。
       pandas 是“先按逗号切列”再解析数值，thousands=',' 救不了，
       必须在切列前把千分位碎片合并回所属列。
    """
    with open(path, 'r', encoding=encoding, newline='') as f:
        lines = [ln for ln in f.read().splitlines() if ln.strip()]

    ncols = len(lines[0].split(','))   # 以表头列数为锚

    def _is_number(s):
        try:
            return s.strip() != '' and float(s) is not None
        except ValueError:
            return False

    fixed = [lines[0]]
    for line in lines[1:]:
        parts = line.split(',')

        # 本就对齐的行：原样保留，绝不误合并
        if len(parts) == ncols:
            fixed.append(line)
            continue

        # 段数多于表头 → 存在被错切的千分位，逐段贪心回拼
        merged = [parts[0]]
        for seg in parts[1:]:
            prev = merged[-1]
            # 假逗号特征：前段以数字结尾 + 本段以“恰好3位数字”开头 + 合并后仍是合法数字
            if (re.search(r'\d$', prev)
                    and re.match(r'^\d{3}(?!\d)', seg)
                    and _is_number(prev + seg)):
                merged[-1] = prev + seg
            else:
                merged.append(seg)

        if len(merged) != ncols:
            raise ValueError(f'列数不齐（期望{ncols}，实得{len(merged)}）：{line}')
        fixed.append(','.join(merged))

    return pd.read_csv(io.StringIO('\n'.join(fixed)))


try:
    df = read_thousand_sep_csv(file_path)

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
# 场景 A：整个文件的所有行都少了一列（表头和数据行一致），结果：不会报错。
# 场景 B：只有部分数据行多了一列（表头有 5 列，但某行有 6 列），结果：会直接抛出 ParserError（解析错误）。
# 场景 C：只有部分数据行少了一列（表头有 5 列，但某行有 4 列），结果：静默补了个NaN。
# 2、如果文件路径带中文和空格，还能跑吗？
# 答：可以正常运行。
# 3、你打印出来的"行数"，包含表头吗？
# 答：不包含，表头是列名。
#我对源文件前3行的数字，核了“营业收入_亿元、归母净利润_亿元、roe_pct、资产负债率_pct”四列的数值，发现它们与源文件完全一致，说明脚本正确处理了千分位逗号问题。

