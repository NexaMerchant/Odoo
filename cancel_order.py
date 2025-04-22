import logging
from odoo import api, fields, models, tools, SUPERUSER_ID
from odoo.modules.registry import Registry
import odoo

# 初始化日志
# _logger = logging.getLogger(__name__)

def parse_args():
    parser = argparse.ArgumentParser(description='获取 Odoo 模型字段值')
    parser.add_argument('-m', '--model', required=True, help='模型名称（如 sale.order）')
    parser.add_argument('-i', '--id', type=int, required=True, help='记录ID')
    # parser.add_argument('-f', '--field', required=True, help='字段名称')
    parser.add_argument('-c', '--config', default='odoo.conf', help='Odoo 配置文件路径')
    return parser.parse_args()

def exec_cancel():
    args = parse_args()

    # 加载 Odoo 配置
    odoo.tools.config.parse_config(['-c', args.config])

    # 初始化数据库连接
    db_name = odoo.tools.config['db_name']
    registry = Registry(db_name)

    with registry.cursor() as cr:
        env = api.Environment(cr, SUPERUSER_ID, {})

        # 获取记录和字段
        orders = env[args.model].sudo().search([
            ('state', 'in', ['sale'])
        ])

        # 逐个执行取消
        for order in orders:
            print(order.name)
            order.action_cancel()
            # 刷新缓存
            order.invalidate_cache()
            if order.state == 'cancel':
                print(f"删除订单：{order.name}")
                order.unlink()
            else:
                print(f"无法取消订单：{order.name}，当前状态：{order.state}")


if __name__ == '__main__':
    exec_cancel()