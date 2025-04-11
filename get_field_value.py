#!/usr/bin/env python3
"""
Odoo 字段值获取工具
用法：./get_field_value.py -m sale.order -i 1 -f order_line_images
"""
import argparse
import logging
from odoo import api, fields, models, tools, SUPERUSER_ID
from odoo.modules.registry import Registry
import odoo

# 初始化日志
_logger = logging.getLogger(__name__)

def parse_args():
    parser = argparse.ArgumentParser(description='获取 Odoo 模型字段值')
    parser.add_argument('-m', '--model', required=True, help='模型名称（如 sale.order）')
    parser.add_argument('-i', '--id', type=int, required=True, help='记录ID')
    parser.add_argument('-f', '--field', required=True, help='字段名称')
    parser.add_argument('-c', '--config', default='odoo.conf', help='Odoo 配置文件路径')
    return parser.parse_args()

def get_field_value():
    args = parse_args()

    # 加载 Odoo 配置
    odoo.tools.config.parse_config(['-c', args.config])

    # 初始化数据库连接
    db_name = odoo.tools.config['db_name']
    registry = Registry(db_name)

    with registry.cursor() as cr:
        env = api.Environment(cr, SUPERUSER_ID, {})

        # 获取记录和字段
        order = env[args.model].sudo().browse(args.id)
        order.write({'state': 'cancel'})
        order.unlink()
        # 先取消订单所有相关操作
        # for invoice in order.invoice_ids:
        #     invoice.button_draft()
        #     invoice.button_cancel()
        #     invoice.unlink()

        # for picking in order.picking_ids:
        #     picking.action_cancel()
        #     picking.unlink()

        # order.action_cancel()
        # order.unlink()

        print("=== 记录信息 ===")

        # field = record._fields.get(args.field)

        # if not field:
        #     _logger.error(f"字段 {args.field} 不存在于模型 {args.model}")
        #     return

        # # 输出字段信息
        # print(f"\n[模型] {args.model} (ID: {args.id})")
        # print(f"[字段] {args.field} (类型: {field.type})")
        # print(f"[存储] {'是' if field.store else '否'} | {'计算字段' if field.compute else '普通字段'}")

        # # 获取字段值
        # value = record[args.field]
        # print("\n=== 字段值 ===")
        # print(value if value is not None else "NULL")

if __name__ == '__main__':
    get_field_value()