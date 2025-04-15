import json
from odoo import http, fields
from odoo.http import request, Response
from odoo.exceptions import UserError, AccessError,AccessDenied
import werkzeug
import logging
import os
import datetime
from odoo.tools import config
import traceback
import sys
import requests
import base64
import redis
from time import sleep
from PIL import Image
from decimal import Decimal, ROUND_HALF_UP

_logger = logging.getLogger(__name__)

class OrderController(http.Controller):
    _name = 'nexamerchant.order'
    _description = 'Order Management'

    @http.route('/api/nexamerchant/order', type='json', auth='public', methods=['POST'], csrf=True, cors='*')
    def create_order(self, **kwargs):
        """
        创建订单接口
        """

        # return {
        #     'success': False,
        #     'message': 'No data provided',
        #     'status': 400
        # }

        # 鉴权
        request_token = request.httprequest.headers.get('Authorization')
        expected_token = request.env['ir.config_parameter'].sudo().get_param('nexa.api_token')
        if not request_token or request_token != f'Bearer {expected_token}':
            raise werkzeug.exceptions.Forbidden("Invalid or missing token.")

        response = {
            'success': False,
            'message': '',
        }

        # return response

        redis_host = config['redis_host']
        redis_port = config['redis_port']
        redis_db = config['redis_db']
        redis_password = config['redis_password']
        redis_obj = redis.Redis(host=redis_host, port=redis_port, db=redis_db, password=redis_password)

        try:
            # 获取请求数据
            data = request.httprequest.data
            if not data:
                return {
                    'success': False,
                    'message': 'No data provided',
                    'status': 400
                }

            data = json.loads(data)
            order = data.get('order')

            # 获取国家id
            country = self._get_country(data)
            if not country or not country.id:
                return {
                    'success': False,
                    'message': '国家信息获取失败' + json.dumps(order['shipping_address']),
                    'status': 401
                }

            # 获取区域id
            state = self._get_state(data, country.id)
            if not state or not state.id:
                return {
                    'success': False,
                    'message': '区域信息获取失败' + json.dumps(order['shipping_address']),
                    'status': 401
                }

            # 获取客户id
            customer = self._get_customer(data, state.id, country.id)

            # 获取货币id
            currency = self._get_currency(data)

            order_info = request.env['sale.order'].sudo().search([
                ('origin', '=', order['order_number']),
            ], limit=1)

            is_add = False
            if order_info:
                order_id = order_info.id
            else:
                # 新增
                try:
                    order_info = self._create_order(data, customer.id, currency.id)
                    order_id = order_info.id
                    is_add = True
                except Exception as e:
                    # print('An exception occurred')
                    #     _logger.error("Failed to _create_order: %s", str(e))
                    #     raise ValueError("Failed to _create_order: %s", str(e))
                    return {
                        'success': False,
                        'message': '订单创建失败3:' + str(e),
                        'status': 401
                    }

            products_data = []

            # 处理订单详情
            for item in order['line_items']:
                variant = self._create_product_attributes(item, redis_obj) # 创建商品属性并返回变体值
                variant_id = variant.id
                if variant_id:

                    price_unit = Decimal(str(item['price']))
                    qty = Decimal(str(item['qty_ordered']))
                    discount_amount = Decimal(str(item['discount_amount']))

                    # 计算折扣值 保留四位小数
                    if price_unit * qty != 0:
                        # 单价 =（总价 - 总折扣） / 数量
                        discount_percent = (discount_amount / (price_unit * qty)) * Decimal('100')
                        discount_percent = discount_percent.quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)
                    else:
                        discount_percent = Decimal('0.0')


                    # 计算实际单价 保留四位小数
                    # if qty != 0:
                    #     # 单价 =（总价 - 总折扣） / 数量
                    #     actual_price_unit = (price_unit * qty - discount_amount) / qty
                    #     # 关键点：使用 quantize 保留4位小数，并指定四舍五入模式
                    #     actual_price_unit = actual_price_unit.quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)
                    # else:
                    #     actual_price_unit = Decimal('0.0000')

                    # return {
                    #     'order_id': order_id,
                    #     'product_id': variant_id,
                    #     'product_uom_qty': qty,
                    #     'price_unit': actual_price_unit,
                    #     'currency_id': currency.id,
                    #     # 'discount': discount_percent
                    # }

                    # 创建订单详情
                    request.env['sale.order.line'].sudo().search([
                        ('order_id', '=', order_id),
                        ('product_id', '=', variant_id)
                    ], limit=1) or request.env['sale.order.line'].sudo().create({
                            'order_id': order_id,
                            'product_id': variant_id,
                            'product_uom_qty': qty,
                            'price_unit': price_unit,
                            'currency_id': currency.id,
                            'discount': discount_percent
                        })

                    redis_key = config['odoo_product_id_hash_key'] + ':' + config['app_env']
                    redis_field = item.get('default_code').lower()
                    product_data = {
                        'name': item.get('name', ''),
                        'description': item['sku'].get('description', ''),
                        'list_price': float(item.get('price', 0)),
                        'type': 'consu',
                        'product_id': redis_obj.hget(redis_key, redis_field),
                        'default_code': item.get('default_code', ''),
                        'currency_id': currency.id,
                        'uom_id': variant.product_tmpl_id.uom_id.id,
                        'categ_id': variant.product_tmpl_id.categ_id.id,
                    }
                    products_data.append(product_data)

            if is_add:
                payment_info = order.get('payment')
                method_str = payment_info.get('method')
                # return payment_info
                # try:
                #     invoice = order_info._create_invoices()
                #     invoice.action_post()
                # except:
                #     print('An exception occurred')
                #     pass
                journal_id = self._get_journal_id('bank')
                payment_method_id = self._get_payment_method_id(method_str)
                payment = request.env['account.payment'].sudo().create({
                    'payment_type': 'inbound',  # 收款为 inbound, 付款为 outbound
                    'partner_type': 'customer',  # 客户为 customer, 供应商为 supplier
                    'partner_id': int(customer.id),
                    'amount': float(order['grand_total']),
                    'payment_method_id': payment_method_id,
                    'journal_id': journal_id,  # 比如现金、银行账户的 journal
                })
                payment.action_post()

            # 构建成功响应
            try:
                customer_fields = request.env['res.partner'].fields_get().keys()
                customer_info = customer.read(list(customer_fields))[0]
                # customer_info = customer.read()[0] if customer and hasattr(customer, 'read') else {}
                # return customer_info.keys()
                if 'avatar_1920' in customer_info.keys():
                    del customer_info['avatar_1920']
                    del customer_info['avatar_1024']
                    del customer_info['avatar_512']
                    del customer_info['avatar_256']
                    del customer_info['avatar_128']

                order_fields = request.env['sale.order'].fields_get().keys()
                order_info = order_info.read(list(order_fields))[0]
                # order_info = order_info.read()[0] if order_info and hasattr(order_info, 'read') else {}
                if 'order_line_images' in order_info.keys():
                    del order_info['order_line_images']
                    if 'product_image' in order_info.keys():
                        del order_info['product_image']
            except Exception as e:
                print('An exception occurred')
                _, _, tb = sys.exc_info()
                line_number = tb.tb_lineno
                return {
                    'success': True,
                    'message': '订单创建成功 but' + str(e) + '.line_number:' + str(line_number),
                    'data': {
                        'customer_data': {},
                        'product_data': product_data,
                        'order_data': {},
                    }
                }

            response.update({
                'success': True,
                'message': '订单创建成功',
                'data': {
                    'customer_data': customer_info,
                    'product_data': products_data,
                    'order_data': order_info,
                }
            })

        except ValueError as ve:
            _logger.error(f"验证错误: {str(ve)}")
            # 打印异常信息 + 行号
            traceback.print_exc()  # 打印完整堆栈（包括行号）
            # 或者只获取当前异常的行号
            _, _, tb = sys.exc_info()
            line_number = tb.tb_lineno
            response['message'] = f"数据验证错误: {str(ve)} line:{str(line_number)}"

        except Exception as e:

            _logger.exception(f"订单创建失败1: {str(e)}")

            # 打印异常信息 + 行号
            traceback.print_exc()  # 打印完整堆栈（包括行号）
            # 或者只获取当前异常的行号
            _, _, tb = sys.exc_info()
            line_number = tb.tb_lineno
            response['message'] = f"订单创建失败2: {str(e)} line:{str(line_number)}"

        return response

    def _add_shipping_cost(self, order_id, price_unit):
        """
        在 Odoo 16 订单上添加运费
        """
        # 通过 default_code找到运费产品
        delivery_product = request.env['product.product'].sudo().search([
            ('default_code', '=', config['delivery_default_code'])
        ], limit=1)

        if not delivery_product:
            raise ValueError("未找到运费产品，请检查配置")

        # 在订单中添加运费
        request.env['sale.order.line'].sudo().search([
            ('order_id', '=', order_id),
            ('product_id', '=', delivery_product.id)
        ]) or request.env['sale.order.line'].sudo().create({
            'order_id': order_id,
            'product_id': delivery_product.id,
            'name': 'Shipping Fee',  # 运费名称
            'product_uom_qty': 1,  # 运费默认数量 1
            'price_unit': float(price_unit),  # 运费金额
            'is_delivery': True
        })

        return True

    def _create_product_attributes(self, item, redis_obj):
        """
        创建商品属性 并返回变体值
        1.商品属性: product.attribute
        2.属性值: product.attribute.value
        3.商品模板(spu): product.template
        4.商品模板允许的属性: product.template.attribute.line
        5.商品模板允许的属性的值: product.template.attribute.value(根据笛卡尔积自动生成记录)
        6.商品变体(sku): product.product(根据笛卡尔积自动生成记录)
        """
        try:
            sku = item.get('sku', {})
            attributes = sku.get('attributes', {})

            # 查找或创建spu
            default_code = item.get('default_code').lower()
            redis_key = config['odoo_product_id_hash_key'] + ':' + config['app_env']
            redis_field = f'{default_code}'
            product_template_id = redis_obj.hget(redis_key, redis_field)
            if not product_template_id:
                product_template = request.env['product.template'].sudo().search([
                    ('default_code', '=', default_code),
                ], limit=1)
                if not product_template:
                    product_template = request.env['product.template'].sudo().create({
                        'name': item.get('name', ''),
                        'description': sku.get('description', ''),
                        'list_price': float(item.get('price', 0)),
                        'type': 'consu',
                    })
                    product_template_id = product_template.id
                else:
                    product_template_id = product_template.id

                redis_obj.hset(redis_key, redis_field, int(product_template_id))

            product_template_id = int(product_template_id)

            # 批量处理属性
            attribute_value_ids = []
            for attribute in attributes:
                attribute_name = attribute.get('attribute_name')
                option_label = attribute.get('option_label')

                if not attribute_name or not option_label:
                    continue

                # 1. 查找或创建属性
                product_attribute = request.env['product.attribute'].sudo().search([
                    ('name', '=', attribute_name),
                    ('create_variant', '=', 'always')
                ], limit=1) or request.env['product.attribute'].sudo().create({
                    'name': attribute_name,
                    'create_variant': 'always',
                })

                # 2. 查找或创建属性值
                attribute_value = request.env['product.attribute.value'].sudo().search([
                    ('name', '=', option_label),
                    ('attribute_id', '=', product_attribute.id)
                ], limit=1) or request.env['product.attribute.value'].sudo().create({
                    'name': option_label,
                    'attribute_id': product_attribute.id
                })
                attribute_value_ids.append(attribute_value.id)

                # 3. 处理属性线
                product_attribute_line = request.env['product.template.attribute.line'].sudo().search([
                    ('product_tmpl_id', '=', product_template_id),
                    ('attribute_id', '=', product_attribute.id),
                ], limit=1)

                if product_attribute_line:
                    existing_value_ids = product_attribute_line.value_ids.mapped('id')
                    if attribute_value.id not in existing_value_ids:
                        product_attribute_line.write({'value_ids': [(4, attribute_value.id)]})
                else:
                    request.env['product.template.attribute.line'].sudo().create({
                        'product_tmpl_id': product_template_id,
                        'attribute_id': product_attribute.id,
                        'value_ids': [(6, 0, [attribute_value.id])],  # 6,0 确保唯一
                    })

            # 4. 查找匹配的变体
            domain = [('product_tmpl_id', '=', product_template_id)]
            if attribute_value_ids:
                domain.append(('product_template_attribute_value_ids.product_attribute_value_id', 'in', attribute_value_ids))
            variants = request.env['product.product'].sudo().search(domain)
            # 找出属性值完全匹配的变体
            for var in variants:
                var_value_ids = set(var.product_template_attribute_value_ids.mapped('product_attribute_value_id.id'))
                if set(attribute_value_ids) == var_value_ids:
                    variant = var
                    break
            else:
                variant = None

            if not variant:
                product_template._create_variant_ids()
                variant = request.env['product.product'].sudo().search(domain, limit=1)

                if not variant:
                    variant = request.env['product.product'].sudo().create({
                        'product_tmpl_id': product_template_id,
                        'attribute_value_ids': [(6, 0, attribute_value_ids)],
                        'default_code': sku.get('product_sku')
                    })

            # 5. 更新变体信息
            update_vals = {
                'default_code': sku.get('product_sku'),
            }
            if sku.get('img'):
                image_base64 = self._get_product_img(variant.id, sku.get('img'))
                if image_base64:
                    update_vals['image_1920'] = image_base64

            variant.sudo().write(update_vals)

            return variant

        except Exception as e:
            _, _, tb = sys.exc_info()
            line_number = tb.tb_lineno
            raise ValueError(f"111 Failed to create product attributes---: { str(e)}. line_number: {line_number}")

    def _get_product_img(self, variant_id, image_src):
        """获取产品图片，支持缓存和重复利用
        Args:
            variant_id: 产品变体ID
            image_src: 图片URL

        Returns:
            base64编码的图片数据
        """
        os.makedirs('images', exist_ok=True)
        image_path = f'images/{variant_id}.jpg'
        temp_path = f'images/{variant_id}.tmp'  # 临时文件路径

        # 1. 如果图片已存在且有效，直接返回
        if os.path.exists(image_path):
            try:
                # 验证现有图片是否有效
                with Image.open(image_path) as img:
                    img.verify()

                # 读取并返回base64编码
                with open(image_path, 'rb') as f:
                    return base64.b64encode(f.read()).decode('utf-8')
            except Exception as e:
                print(f"现有图片损坏，重新下载: {e}")
                os.remove(image_path)  # 删除损坏文件

        # 2. 下载并处理新图片
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0',
                'Accept': 'image/webp,image/*,*/*;q=0.8'
            }
            response = requests.get(image_src, headers=headers, timeout=15)
            response.raise_for_status()

            # 计算文件哈希用于验证
            # file_hash = hashlib.md5(response.content).hexdigest()
            # print(f"下载完成，文件哈希: {file_hash}")

            # 先保存到临时文件
            with open(temp_path, 'wb') as f:
                f.write(response.content)

            # 验证并转换图片
            try:
                with Image.open(temp_path) as img:
                    img.verify()
                    img = Image.open(temp_path)
                    if img.mode != 'RGB':
                        img = img.convert('RGB')
                    img.save(image_path, 'JPEG', quality=95, subsampling=0)
            except Exception as img_error:
                print(f"Pillow处理失败: {img_error}")
                # if not shutil.which('dwebp'):
                #     raise RuntimeError("dwebp工具未安装")
                os.system(f'dwebp {temp_path} -o {image_path}')

            # 最终验证
            with Image.open(image_path) as img:
                img.verify()

            # 读取并返回base64
            with open(image_path, 'rb') as f:
                return base64.b64encode(f.read()).decode('utf-8')

        except Exception as e:
            # 清理可能损坏的文件
            for path in [temp_path, image_path]:
                if os.path.exists(path):
                    os.remove(path)
            raise ValueError(f"图片处理失败: {str(e)}")
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def _format_created_at(self, created_at):
        """格式化日期"""
        parsed_date = datetime.datetime.strptime(created_at, '%Y-%m-%dT%H:%M:%S.%fZ')
        formatted_date = parsed_date.strftime('%Y-%m-%d %H:%M:%S')
        return formatted_date

    def _create_order(self, data, customer_id, currency_id):
        """创建订单"""
        # try:
        order = data.get('order')

        formatted_date = self._format_created_at(order['created_at'])

        order_data = {
            'partner_id'    : int(customer_id),
            'origin'        : order['order_number'],
            'date_order'    : formatted_date,
            'state'         : 'sale',
            'create_date'   : formatted_date,
            'invoice_status': 'to invoice',
            'currency_id'   : currency_id,
            'amount_total'  : float(order['grand_total']),
            'amount_tax'    : float(order['tax_amount']),
            'warehouse_id'  : self._get_warehouse_id(order),
            'name'          : order['name'],
            'website_id'    : self._get_website_id(order['website_name']),
        }
        new_order = request.env['sale.order'].sudo().create(order_data)
        new_order.action_confirm()
        # except Exception as e:
        #     _logger.error("Failed to _create_order: %s", str(e))
        #     raise ValueError("Failed to _create_order: %s", str(e))

        # print(order_data)

        return new_order

    def _get_payment_method_id(self, payment_name):
        """
        获取付款方式的ID，根据支付名称映射匹配 account.payment.method
        """
        payment_mapping = {
            'paypal_smart_button': 'paypal',
            'airwallex': 'airwallex',
            'codpayment': 'cod',
        }
        code = payment_mapping.get(payment_name)
        payment_method = request.env['account.payment.method'].sudo().search([
            ('code', '=', code),
            ('payment_type', '=', 'inbound')
        ], limit=1)

        if not payment_method:
            raise ValueError(f"[PaymentMethod] Not found: code:{code} payment_name:{payment_name} ")

        return payment_method.id


    def _get_journal_id(self, type='bank'):
        """
        获取支付方式对应的账户（Journal）的ID
        """

        journal = request.env['account.journal'].sudo().search([
            ('type', '=', type),
        ], limit=1)

        if not journal:
            raise ValueError(f"[Journal] Not found: ({type})")

        return journal.id

    def _get_website_id(self, website_name):
        web_site = request.env['website'].sudo().search([
            ('name', '=', website_name),
        ], limit=1)

        if not web_site:
            raise ValueError(f"[WebSite] Not found: ({website_name})")

        return web_site.id


    def _get_currency(self, data):
        """获取币种ID"""
        order = data.get('order')
        currency = request.env['res.currency'].sudo().search([('name', '=', order['currency'])], limit=1)
        if not currency:
            raise ValueError("Currency not found")
        return currency

    def _get_state(self, data, country_id):
        """获取区域ID"""
        order = data.get('order')
        shipping_address = order.get('shipping_address')
        code = shipping_address.get('province')
        search_where = []
        if code:
            search_where.append(('code', '=', code))
        if country_id:
            search_where.append(('country_id', '=', country_id))

        state = request.env['res.country.state'].sudo().search(search_where, limit=1)
        # state = request.env['res.country.state'].sudo().search([
        #     ('code', '=', code),
        #     ('country_id', '=', country_id)
        # ], limit=1)

        if not state:
            raise ValueError(f"State not found code={code} and country_id={country_id}")
        return state

    def _get_country(self, data):
        """获取国家ID"""
        order = data.get('order')
        country = request.env['res.country'].sudo().search([('code', '=', order['shipping_address']['country'])], limit=1)
        if not country:
            raise ValueError("Country not found")
        return country

    def _get_customer(self, data, state_id, country_id):
        """获取客户ID"""
        order = data.get('order')
        customer = order.get('customer')
        try:
            customer_info = request.env['res.partner'].sudo().search([('email', '=', customer.get('email'))], limit=1)
            if not customer_info:
                customer_data = {
                    'name'        : order['shipping_address']['first_name'] + ' ' + order['shipping_address']['last_name'],
                    'email'       : customer['email'],
                    'phone'       : order['shipping_address']['phone'],
                    'street'      : order['shipping_address']['address1'],
                    'city'        : order['shipping_address']['city'],
                    'zip'         : order['shipping_address']['zip'],
                    'country_code': order['shipping_address']['country'],
                    'state_id'    : state_id,
                    'country_id'  : country_id,
                    'website_id'  : config['usa_website_id'],
                    # 'lang'        : config['usa_lang'],
                    # 'category_id' : [8],
                    'type'        : 'delivery',
                }

                # return customer_data

                customer_info = request.env['res.partner'].sudo().create(customer_data)

            if not customer_info:
                raise ValueError("客户不存在")

        except Exception as e:
            _logger.error("Failed to get_customer_id: %s", str(e))
            raise ValueError("Failed to get_customer_id: %s", str(e))

        return customer_info

    def _get_warehouse_id(self, order):
        """
        根据支付方式获取仓库 ID
        """

        payment_info = order.get('payment')
        payment_method = payment_info.get('method')

        # 动态设置仓库 ID
        if payment_method in ['paypal_smart_button', 'airwallex']:
            warehouse_id = request.env['stock.warehouse'].sudo().search([('name', '=', '上海')], limit=1).id
        elif payment_method:
            warehouse_id = request.env['stock.warehouse'].sudo().search([('name', '=', '深圳')], limit=1).id

        return warehouse_id

    def _validate_order_data(self, data):
        """验证订单数据"""
        required_fields = ['lines']
        for field in required_fields:
            if field not in data:
                raise ValueError(f"缺少必填字段: {field}")

        if not isinstance(data.get('lines'), list) or len(data['lines']) == 0:
            raise ValueError("订单必须包含至少一个商品")

    @http.route('/api/nexamerchant/order/<int:order_id>', type='json', auth='public', methods=['PUT'], csrf=False)
    def update_order(self, order_id, **kwargs):
        # 处理更新订单的逻辑
        pass

    @http.route('/api/nexamerchant/order/<int:order_id>', type='http', auth='public', methods=['GET'], csrf=False)
    def get_order(self, order_id, **kwargs):
        print('hellow world')
        # 处理获取订单的逻辑
        pass