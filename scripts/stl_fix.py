#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把 STL 模型摆正：XY 居中，最低点贴到地面（z = 0）。

纯 Python 标准库实现 —— 不需要安装任何第三方库（没有 trimesh、没有 numpy 也能跑）。

用法：
    python3 stl_fix.py 模型.stl            # 输出 模型_onbed.stl
    python3 stl_fix.py 模型.stl 输出.stl    # 指定输出文件名

它做什么：
    1. 读出模型的长宽高（对照你的打印机能不能放得下）
    2. 把模型挪到打印板正中央
    3. 把模型抬到板面上（不会有一半陷进板子里）

AI 生成的 3D 模型原点位置通常是随机的，所以经常一打开就是歪的、陷进板子里的。
跑一遍这个脚本就正了。
"""

import os
import struct
import sys

HEADER_SIZE = 80
COUNT_SIZE = 4
TRIANGLE_SIZE = 50          # 12 个 float + 1 个 uint16
FLOAT_COUNT = 12


def read_binary_stl(path):
    """读出所有三角面。返回 (文件头, 三角面数据块)。"""
    with open(path, 'rb') as f:
        raw = f.read()

    if len(raw) < HEADER_SIZE + COUNT_SIZE:
        raise ValueError('文件太小，不像是一个有效的 STL 文件')

    header = raw[:HEADER_SIZE]
    count = struct.unpack('<I', raw[HEADER_SIZE:HEADER_SIZE + COUNT_SIZE])[0]

    expected = HEADER_SIZE + COUNT_SIZE + count * TRIANGLE_SIZE
    if len(raw) != expected:
        # 面数对不上，多半是 ASCII 格式的 STL
        raise ValueError(
            '这个 STL 不是二进制格式（可能是 ASCII 格式），本脚本暂不支持。\n'
            '请在导出时选择「二进制 STL / Binary STL」。'
        )

    body = raw[HEADER_SIZE + COUNT_SIZE:]
    return header, count, body


def compute_bounds(body, count):
    """扫一遍所有顶点，算出包围盒。"""
    min_x = min_y = min_z = float('inf')
    max_x = max_y = max_z = float('-inf')

    # 每个三角面 12 个 float：法向量(3) + 三个顶点(各3) + 1 个属性字节
    for vals in struct.iter_unpack('<12fH', body):
        for i in (3, 6, 9):
            x, y, z = vals[i], vals[i + 1], vals[i + 2]
            if x < min_x: min_x = x
            if y < min_y: min_y = y
            if z < min_z: min_z = z
            if x > max_x: max_x = x
            if y > max_y: max_y = y
            if z > max_z: max_z = z

    return (min_x, min_y, min_z), (max_x, max_y, max_z)


def shift_stl(body, count, dx, dy, dz):
    """把所有顶点平移 (dx, dy, dz)。法向量不受平移影响，原样保留。"""
    out = bytearray()
    for vals in struct.iter_unpack('<12fH', body):
        packed = (
            vals[0], vals[1], vals[2],                              # 法向量，不动
            vals[3] + dx, vals[4] + dy, vals[5] + dz,               # 顶点 1
            vals[6] + dx, vals[7] + dy, vals[8] + dz,               # 顶点 2
            vals[9] + dx, vals[10] + dy, vals[11] + dz,             # 顶点 3
            vals[12],                                               # 属性字节，原样保留
        )
        out += struct.pack('<12fH', *packed)
    return bytes(out)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    src = sys.argv[1]
    if not os.path.isfile(src):
        print('找不到文件：' + src)
        sys.exit(1)

    base, ext = os.path.splitext(src)
    dst = sys.argv[2] if len(sys.argv) > 2 else base + '_onbed' + (ext or '.stl')

    header, count, body = read_binary_stl(src)
    (min_x, min_y, min_z), (max_x, max_y, max_z) = compute_bounds(body, count)

    size_x = max_x - min_x
    size_y = max_y - min_y
    size_z = max_z - min_z
    print('原始尺寸：%.1f x %.1f x %.1f mm' % (size_x, size_y, size_z))
    print('三角面数：%d' % count)

    dx = -(min_x + max_x) / 2.0     # 左右居中
    dy = -(min_y + max_y) / 2.0     # 前后居中
    dz = -min_z                     # 底面贴地

    print('平移量：dx=%.2f  dy=%.2f  dz=%.2f' % (dx, dy, dz))

    new_body = shift_stl(body, count, dx, dy, dz)

    with open(dst, 'wb') as f:
        f.write(header)
        f.write(struct.pack('<I', count))
        f.write(new_body)

    print('已保存：' + dst)
    print('现在模型是 %.1f x %.1f x %.1f mm，居中立在打印板上。' % (size_x, size_y, size_z))


if __name__ == '__main__':
    main()
