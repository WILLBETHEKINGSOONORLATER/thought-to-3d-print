#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
一键准备参数化建模环境（只有「路径 B」需要用到）。

给谁用：**AI 自己**，不是用户。用户不需要运行这个脚本，也不需要装任何东西。
作用：建一个独立的 Python 虚拟环境，装好 trimesh / manifold3d / shapely / numpy。

用法:
    python3 setup_env.py                 # 装到默认位置
    python3 setup_env.py /自定义/路径     # 装到指定位置

装完会把该环境的 python 绝对路径打印出来，后面跑 param_shell.py 就用它。
"""
import os
import subprocess
import sys

DEFAULT_VENV = os.path.join(
    os.path.expanduser('~'), '.workbuddy', 'binaries', 'python', 'envs', 'mesh'
)
PKGS = ['trimesh', 'manifold3d', 'shapely', 'numpy', 'scipy', 'pillow']


def bin_dir(venv):
    return os.path.join(venv, 'Scripts' if os.name == 'nt' else 'bin')


def py_in(venv):
    return os.path.join(bin_dir(venv), 'python.exe' if os.name == 'nt' else 'python')


def run(cmd, **kw):
    print('  $ ' + ' '.join(cmd))
    return subprocess.run(cmd, check=False, **kw).returncode


def main():
    # 让输出实时刷出来（被管道接住时默认是块缓冲，会看不清进度）
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass

    venv = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_VENV
    print('=' * 70)
    print('参数化建模环境准备（AI 侧执行，用户无需操作）')
    print('=' * 70)
    print('目标环境：' + venv)

    if not os.path.exists(py_in(venv)):
        print('\n[1/3] 创建虚拟环境 …')
        if run([sys.executable, '-m', 'venv', venv]) != 0:
            print('\n❌ 创建失败。改用系统 Python 试：python3 -m venv <路径>')
            return 1
    else:
        print('\n[1/3] 已有虚拟环境，跳过创建')

    py = py_in(venv)

    print('\n[2/3] 升级 pip …')
    run([py, '-m', 'pip', 'install', '--quiet', '--upgrade', 'pip'])

    print('\n[3/3] 安装依赖：' + ' / '.join(PKGS))
    if run([py, '-m', 'pip', 'install', '--quiet'] + PKGS) != 0:
        print('\n❌ 安装失败。若在国内网络，可加镜像：')
        print('   %s -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple %s'
              % (py, ' '.join(PKGS)))
        return 1

    # 验证
    print('\n[验证]')
    code = ('import trimesh, manifold3d, shapely, numpy;'
            'print("trimesh", trimesh.__version__, "| manifold3d OK | shapely", shapely.__version__)')
    if run([py, '-c', code]) != 0:
        print('❌ 验证失败')
        return 1

    print('\n' + '=' * 70)
    print('✅ 环境就绪。后续生成模型请用这个 python：')
    print(py)
    print('=' * 70)
    print('\n下一步示例：')
    print('  %s %s --report' % (py, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'param_shell.py')))
    return 0


if __name__ == '__main__':
    sys.exit(main())
