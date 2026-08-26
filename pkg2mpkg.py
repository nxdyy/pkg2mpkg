"""
Wallpaper Engine PKG -> MPKG 转换工具 (保留全部内容版)

功能：
1. 将 PKG 格式转换为 MPKG 格式（替换 Magic 标识）
2. 保留所有内容（包括音频）
3. 从参考 MPKG 中仅提取 project.json 和 preview.gif
4. .tex 纹理自动使用移动版（DXT->ETC2/ASTC 格式转换）
5. 着色器文件使用 MPKG 版本（移动端适配）
6. scene.json 始终使用 PKG 版本（保留音频引用等配置）
7. 正确重建条目表和偏移量

用法：
    python pkg2mpkg.py <input.pkg> <reference.mpkg> [output.mpkg]

参数：
    input.pkg     - 原始 PKG 文件
    reference.mpkg - 官方 MPKG 文件（用于提取 project.json 等元数据）
    output.mpkg   - 输出文件路径（可选，默认为 input_converted.mpkg）
"""

import struct
import sys
import os


def read_string_i32(data: bytes, offset: int) -> tuple:
    """读取 int32 长度前缀的 UTF-8 字符串"""
    size = struct.unpack_from('<i', data, offset)[0]
    offset += 4
    s = data[offset:offset + size].decode('utf-8')
    offset += size
    return s, offset


def write_string_i32(s: str) -> bytes:
    """写入 int32 长度前缀的 UTF-8 字符串"""
    encoded = s.encode('utf-8')
    return struct.pack('<i', len(encoded)) + encoded


def parse_pkg(filepath: str) -> dict:
    """解析 PKG/MPKG 文件，返回结构化数据"""
    with open(filepath, 'rb') as f:
        data = f.read()

    magic, offset = read_string_i32(data, 0)
    entry_count = struct.unpack_from('<i', data, offset)[0]
    offset += 4

    entries = []
    for i in range(entry_count):
        path, offset = read_string_i32(data, offset)
        entry_offset = struct.unpack_from('<i', data, offset)[0]
        offset += 4
        entry_length = struct.unpack_from('<i', data, offset)[0]
        offset += 4
        entries.append({
            'path': path,
            'offset': entry_offset,
            'length': entry_length
        })

    data_start = offset

    # 提取每个条目的数据
    for entry in entries:
        abs_offset = data_start + entry['offset']
        entry['data'] = data[abs_offset:abs_offset + entry['length']]

    return {
        'magic': magic,
        'entry_count': entry_count,
        'entries': entries,
        'data_start': data_start
    }


def analyze_pkg(filepath: str):
    """分析 PKG/MPKG 文件结构并打印信息"""
    pkg = parse_pkg(filepath)

    print(f"文件: {filepath}")
    print(f"Magic: {pkg['magic']}")
    print(f"条目数量: {pkg['entry_count']}")
    print(f"{'='*70}")

    for i, entry in enumerate(pkg['entries']):
        ext = os.path.splitext(entry['path'])[1]
        print(f"  [{i+1:3d}] {entry['path']:<60s} {entry['length']:>10,} bytes  ({ext})")

    total_size = sum(e['length'] for e in pkg['entries'])
    print(f"{'='*70}")
    print(f"数据总量: {total_size:,} bytes")


def convert_pkg_to_mpkg(input_path: str, reference_path: str, output_path: str = None):
    """
    将 PKG 文件转换为 MPKG 格式。

    转换策略：
    1. 以 PKG 为基础（保留所有内容，包括音频和原始分辨率纹理）
    2. 从参考 MPKG 中仅提取 project.json 和 preview.gif
    3. .tex 纹理文件：PC版用DXT格式，移动端用ETC2/ASTC格式，必须使用移动版
    4. .frag/.vert 着色器文件使用 MPKG 版本（移动端适配）
    5. scene.json 始终使用 PKG 版本（保留音频引用等配置）
    6. 使用 PKGM Magic 重新打包
    """
    if output_path is None:
        base = os.path.splitext(input_path)[0]
        output_path = base + '_converted.mpkg'

    print(f"正在解析 PKG: {input_path}")
    pkg = parse_pkg(input_path)

    print(f"正在解析参考 MPKG: {reference_path}")
    mpkg = parse_pkg(reference_path)

    # 构建 PKG 条目字典（路径 -> 条目）
    pkg_entries = {e['path']: e for e in pkg['entries']}
    mpkg_entries = {e['path']: e for e in mpkg['entries']}

    # 最终条目列表
    final_entries = []

    # 1. 从参考 MPKG 中仅提取必需的元数据文件（project.json, preview.gif）
    # 注意：不提取其他文件，因为参考 MPKG 可能是不同的壁纸
    REFERENCE_FILES = {'project.json', 'preview.gif'}
    for mpkg_entry in mpkg['entries']:
        path = mpkg_entry['path']
        if path in REFERENCE_FILES and path not in pkg_entries:
            print(f"  [添加] {path} (从参考MPKG)")
            final_entries.append({
                'path': path,
                'data': mpkg_entry['data']
            })

    # 2. 处理 PKG 中的所有条目
    for pkg_entry in pkg['entries']:
        path = pkg_entry['path']
        if path in mpkg_entries:
            mpkg_data = mpkg_entries[path]['data']
            pkg_data = pkg_entry['data']

            # 需要使用 MPKG 版本的文件类型：
            # - .tex 纹理文件：PC版用DXT格式(4/7)，移动端用ETC2/ASTC格式(5)，必须替换
            # - .frag/.vert 着色器文件：移动端有适配版本
            use_mpkg = False

            if path.endswith('.tex') and len(pkg_data) != len(mpkg_data):
                use_mpkg = True
                # 检测纹理格式差异
                pc_fmt = struct.unpack_from('<i', pkg_data, 18)[0] if len(pkg_data) > 22 else -1
                mb_fmt = struct.unpack_from('<i', mpkg_data, 18)[0] if len(mpkg_data) > 22 else -1
                fmt_names = {0: 'RGBA8888', 4: 'DXT5', 7: 'DXT1', 5: 'ETC2/ASTC'}
                pc_name = fmt_names.get(pc_fmt, f'Unknown({pc_fmt})')
                mb_name = fmt_names.get(mb_fmt, f'Unknown({mb_fmt})')
                print(f"  [替换] {path} (纹理格式: {pc_name}->{mb_name}, {len(pkg_data):,}->{len(mpkg_data):,} bytes)")
            elif path.endswith(('.frag', '.vert')) and len(pkg_data) != len(mpkg_data):
                use_mpkg = True
                print(f"  [替换] {path} (着色器: {len(pkg_data):,}->{len(mpkg_data):,} bytes)")

            if use_mpkg:
                final_entries.append({
                    'path': path,
                    'data': mpkg_data
                })
            else:
                final_entries.append({
                    'path': path,
                    'data': pkg_data
                })
        else:
            # 仅在 PKG 中的条目（如音频文件），直接保留
            print(f"  [保留] {path} ({pkg_entry['length']:,} bytes)")
            final_entries.append({
                'path': path,
                'data': pkg_entry['data']
            })

    # 3. 构建 MPKG 文件
    new_magic = "PKGM0020"

    # 写入 Magic
    output = write_string_i32(new_magic)

    # 写入条目数量
    output += struct.pack('<i', len(final_entries))

    # 计算数据区偏移
    current_data_offset = 0
    headers = b''
    body = b''

    for entry in final_entries:
        # 写入条目头部
        headers += write_string_i32(entry['path'])
        headers += struct.pack('<i', current_data_offset)
        headers += struct.pack('<i', len(entry['data']))

        # 写入数据
        body += entry['data']
        current_data_offset += len(entry['data'])

    output += headers + body

    # 写入文件
    with open(output_path, 'wb') as f:
        f.write(output)

    print(f"\n{'='*70}")
    print(f"转换完成！")
    print(f"  原始 Magic: {pkg['magic']}")
    print(f"  新 Magic: {new_magic}")
    print(f"  条目数量: {len(final_entries)}")
    print(f"  输出文件: {output_path}")
    print(f"  输出大小: {len(output):,} bytes")

    return output_path


def main():
    if len(sys.argv) < 2:
        print("Wallpaper Engine PKG -> MPKG 转换工具")
        print()
        print("用法:")
        print(f"  分析: python {sys.argv[0]} <file.pkg|file.mpkg> --analyze")
        print(f"  转换: python {sys.argv[0]} <input.pkg> <reference.mpkg> [output.mpkg]")
        print()
        print("参数说明:")
        print("  input.pkg      - 原始 PKG 文件")
        print("  reference.mpkg - 官方 MPKG 文件（用于提取元数据和适配内容）")
        print("  output.mpkg    - 输出文件路径（可选）")
        sys.exit(1)

    input_path = sys.argv[1]

    if not os.path.exists(input_path):
        print(f"错误: 文件不存在 - {input_path}")
        sys.exit(1)

    # 分析模式
    if '--analyze' in sys.argv:
        analyze_pkg(input_path)
        sys.exit(0)

    # 转换模式
    if len(sys.argv) < 3 or sys.argv[2].startswith('--'):
        print("错误: 转换模式需要提供参考 MPKG 文件路径")
        print(f"用法: python {sys.argv[0]} <input.pkg> <reference.mpkg> [output.mpkg]")
        sys.exit(1)

    reference_path = sys.argv[2]
    if not os.path.exists(reference_path):
        print(f"错误: 参考文件不存在 - {reference_path}")
        sys.exit(1)

    output_path = sys.argv[3] if len(sys.argv) > 3 and not sys.argv[3].startswith('--') else None
    convert_pkg_to_mpkg(input_path, reference_path, output_path)


if __name__ == '__main__':
    main()
