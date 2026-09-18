# -*- coding: utf-8 -*-
"""全局运行上下文：数据库连接与"当前小区"状态。"""


class AppContext:
    """在菜单各层之间传递的运行时上下文。

    所有业务数据都挂接在"当前小区"之下：切换小区后各模块自动只展示该小区数据。
    """

    def __init__(self, conn):
        self.conn = conn
        self.community_id = None      # 当前小区 id（None = 未选择）
        self.community_name = None    # 当前小区名称（用于界面标题）

    def set_community(self, row):
        """切换当前小区（row 为 community 表记录）。"""
        self.community_id = row['id']
        self.community_name = row['name']

    def refresh_name(self, cid, name):
        """小区改名后同步标题显示。"""
        if self.community_id == cid:
            self.community_name = name
