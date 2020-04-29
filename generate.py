"""
Copyright (c) 2019 Ash Wilding. All rights reserved.

SPDX-License-Identifier: MIT

Run the arm64-pgtable-tool.
"""

from sys import version_info
if version_info < (3, 8):
    raise Exception("arm64-pgtable-tool requires Python 3.8+")

import pgtt
