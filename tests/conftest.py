# -*- coding: utf-8 -*-
"""确保测试能导入项目根目录模块"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
