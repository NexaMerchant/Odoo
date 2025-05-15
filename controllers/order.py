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

    @http.route('/api/nexamerchant/external_order', type='json', auth='public', methods=['POST'], csrf=True, cors='*')
    def create_external_order(self, **kwargs):
        """
        创建临时订单接口
        """
        # 鉴权
        request_token = request.httprequest.headers.get('Authorization')
        expected_token = request.env['ir.config_parameter'].sudo().get_param('nexa.api_token')
        if not request_token or request_token != f'Bearer {expected_token}':
            raise werkzeug.exceptions.Forbidden("Invalid or missing token.")

        # 获取请求数据
        data = request.httprequest.data
        if not data:
            return {
                'success': False,
                'message': 'No data provided',
                'status': 400
            }

        response = {
            'success': False,
            'message': '',
        }


        try:
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
            state_id = self._get_state(data, country.id)

            # 获取客户id
            customer = self._get_or_create_customer(data, state_id, country.id)
            if not customer:
                return {
                    'success': False,
                    'message': '客户信息获取失败',
                    'status': 401
                }

            # 获取货币id
            pricelist_id, currency_id = self._get_currency(data)

            order_info = request.env['sale.order'].sudo().search([
                ('name', '=', order['name']),
            ], limit=1)

            if order_info:
                return {
                    'success': False,
                    'message': '订单已存在，状态:' + order_info.state,
                    'status': 401
                }
            else:
                # 新增
                try:
                    order_info = self._create_order(data, customer.id, pricelist_id, currency_id)
                    if order_info:
                        order_id = order_info.id
                    else:
                        return {
                            'success': False,
                            'message': '订单创建失败',
                            'status': 401
                        }
                except Exception as e:
                    return {
                        'success': False,
                        'message': '订单创建失败:' + str(e),
                        'status': 401
                    }


            # 处理订单详情
            for item in order['line_items']:
                sku = item['sku']

                images = self._get_product_img(0, sku.get('img'))

                create_data = {
                    'sale_order_id': order_id,
                    'external_name': item.get('name'),
                    'external_sku': sku.get('product_sku'),
                    'quantity': item.get('qty_ordered'),
                    'price_unit': item['price'],
                    'discount_amount': item['discount_amount'],
                    'product_type': 'consu' if item['is_shipping'] else 'product',
                    'product_url': sku.get('product_url'),
                    'images': images,
                    'images_binary': images
                }

                # 先判断是否已配对 若已配对则直接创建订单详情
                external_sku_mapping = request.env['external.sku.mapping'].sudo().search([
                    ('external_sku', '=', sku.get('product_sku'))
                ], limit=1)
                if external_sku_mapping:

                    price_unit = Decimal(str(item['price']))
                    qty = Decimal(str(item['qty_ordered']))
                    discount_amount = Decimal(str(item['discount_amount']))

                    # 计算折扣值 保留四位小数
                    if price_unit * qty != 0:
                        discount_percent = (discount_amount / (price_unit * qty)) * Decimal('100')
                        discount_percent = discount_percent.quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)
                    else:
                        discount_percent = Decimal('0.0')

                    request.env['sale.order.line'].sudo().create({
                        'order_id': order_id,
                        'product_id': external_sku_mapping.product_id.id,
                        'product_uom_qty': item.get('qty_ordered'),
                        'price_unit': item['price'],
                        'currency_id': currency_id,
                        'discount': discount_percent
                    })

                    create_data['product_id'] = external_sku_mapping.product_id.id
                    create_data['confirmed'] = True

                request.env['external.order.line'].sudo().create(create_data)

            customer_info = self.safe_read(customer)
            if 'avatar_1920' in customer_info.keys():
                del customer_info['avatar_1920']
                del customer_info['avatar_1024']
                del customer_info['avatar_512']
                del customer_info['avatar_256']
                del customer_info['avatar_128']
            order_fields = request.env['sale.order'].fields_get().keys()
            order_info = order_info.read(list(order_fields))[0]

            return {
                'success': True,
                'message': '订单创建成功',
                'status': 200,
                'data': {
                    'customer_data': customer_info,
                    'order_data': order_info,
                    'product_data': []
                }
            }

        except Exception as e:
            _, _, tb = sys.exc_info()
            line_number = tb.tb_lineno
            response['message'] = f"订单创建失败: {str(e)} line:{str(line_number)}"

        return response


    @http.route('/api/nexamerchant/order', type='json', auth='public', methods=['POST'], csrf=True, cors='*')
    def sync_order(self, **kwargs):
        """
        创建订单接口
        """

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
            state_id = self._get_state(data, country.id)

            # 获取客户id
            customer = self._get_or_create_customer(data, state_id, country.id)

            # 获取货币id
            pricelist_id, currency_id = self._get_currency(data)

            order_info = request.env['sale.order'].sudo().search([
                ('name', '=', order['name']),
            ], limit=1)

            is_add = False
            if order_info:
                if order_info.state != 'sale':
                    return {
                        'success': False,
                        'message': '订单已存在，状态:' + order_info.state,
                        'status': 401
                    }
                else:
                    return {
                        'success': False,
                        'message': '订单已存在',
                        'status': 401
                    }
                order_id = order_info.id
            else:
                # 新增
                try:
                    order_info = self._create_order(data, customer.id, pricelist_id, currency_id)
                    if order_info:
                        order_id = order_info.id
                        is_add = True
                    else:
                        return {
                            'success': False,
                            'message': '订单创建失败001',
                            'status': 401
                        }
                except Exception as e:
                    return {
                        'success': False,
                        'message': '订单创建失败3:' + str(e),
                        'status': 401
                    }

            products_data = []

            website_name = order['website_name']
            redis_key = self._get_spu_map_redis_key(website_name)

            # 处理订单详情
            for item in order['line_items']:
                variant = self._create_product_attributes(item, redis_obj, redis_key) # 创建商品属性并返回变体值
                variant_id = variant.id
                if variant_id:

                    price_unit = Decimal(str(item['price']))
                    qty = Decimal(str(item['qty_ordered']))
                    discount_amount = Decimal(str(item['discount_amount']))

                    # 计算折扣值 保留四位小数
                    if price_unit * qty != 0:
                        discount_percent = (discount_amount / (price_unit * qty)) * Decimal('100')
                        discount_percent = discount_percent.quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)
                    else:
                        discount_percent = Decimal('0.0')

                    # 创建订单详情
                    request.env['sale.order.line'].sudo().search([
                        ('order_id', '=', order_id),
                        ('product_id', '=', variant_id)
                    ], limit=1) or request.env['sale.order.line'].sudo().create({
                            'order_id': order_id,
                            'product_id': variant_id,
                            'product_uom_qty': qty,
                            'price_unit': price_unit,
                            'currency_id': currency_id,
                            'discount': discount_percent
                        })

                    redis_field = item.get('default_code').lower()
                    product_data = {
                        'name': item.get('name', ''),
                        'description': item['sku'].get('description', ''),
                        'list_price': float(item.get('price', 0)),
                        'type': 'consu',
                        'product_id': redis_obj.hget(redis_key, redis_field),
                        'default_code': item.get('default_code', ''),
                        'currency_id': currency_id,
                        'uom_id': variant.product_tmpl_id.uom_id.id,
                        'categ_id': variant.product_tmpl_id.categ_id.id,
                    }
                    products_data.append(product_data)

            if is_add:
                payment_info = order.get('payment')
                method_str = payment_info.get('method')
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
                customer_info = self.safe_read(customer)
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
            _, _, tb = sys.exc_info()
            line_number = tb.tb_lineno
            response['message'] = f"数据验证错误: {str(ve)} line:{str(line_number)}"

        except Exception as e:
            _, _, tb = sys.exc_info()
            line_number = tb.tb_lineno
            response['message'] = f"订单创建失败: {str(e)} line:{str(line_number)}"

        return response

    def safe_read(self, record, exclude_fields=None):
        """
        安全读取一个记录的字段，自动排除某些可能导致错误的字段。
        :param record: Odoo 记录对象（如 res.partner 的一条记录）
        :param exclude_fields: 要排除的字段列表（如 ['display_name']）
        :return: dict 格式的字段数据
        """
        if not record:
            return {}

        exclude_fields = set(exclude_fields or [])

        # 获取模型字段列表（不包含要排除的字段）
        all_fields = set(record._fields.keys())
        safe_fields = list(all_fields - exclude_fields)

        try:
            result = record.read(safe_fields)
            return result[0] if result else {}
        except Exception as e:
            _logger.warning(f"safe_read failed for {record._name}({record.id}): {e}")
            try:
                fallback_fields = ['id', 'name', 'email', 'phone', 'mobile', 'street', 'street2', 'zip', 'city', 'state_id', 'country_id', 'vat', 'function', 'title', 'company_id', 'category_id', 'user_id', 'team_id', 'lang', 'tz', 'active', 'company_type', 'is_company', 'color', 'partner_share', 'commercial_partner_id', 'type', 'signup_token', 'signup_type', 'signup_expiration', 'signup_url', 'partner_gid']
                result = record.read(fallback_fields)
                return result[0] if result else {}
            except Exception as inner_e:
                _logger.error(f"safe_read fallback also failed: {inner_e}")
                return {}


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

    def _get_spu_map_redis_key(self, website_name):
        # return f'{config['odoo_product_id_hash_key']}:{config['app_env']}'
        return f'{config['odoo_product_id_hash_key']}:{config['app_env']}:{website_name}'

    def _create_product_attributes(self, item, redis_obj, redis_key):
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
                        'type': 'product',
                    })
                    product_template_id = product_template.id
                else:
                    product_template_id = product_template.id

                redis_obj.hset(redis_key, redis_field, int(product_template_id))
            else:
                product_template = request.env['product.template'].sudo().browse(int(product_template_id))

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

            # 获取所有变体
            product_template = request.env['product.template'].sudo().browse(product_template_id)
            self._auto_fill_variant_default_codes(product_template)

            return variant

        except Exception as e:
            _, _, tb = sys.exc_info()
            line_number = tb.tb_lineno
            raise ValueError(f"111 Failed to create product attributes---: { str(e)}. line_number: {line_number}")

    def _auto_fill_variant_default_codes(self, template):
        '''
        自动填充变体的sku
        '''
        for var in template.product_variant_ids:
            if not var.default_code:
                attrs = var.product_template_attribute_value_ids.mapped('product_attribute_value_id.name')
                code_suffix = '-'.join(attrs)
                var.default_code = f"{code_suffix.upper()}"

    def _get_product_img(self, variant_id, image_src):
        """获取产品图片，支持缓存和重复利用
        Args:
            variant_id: 产品变体ID
            image_src: 图片URL

        Returns:
            base64编码的图片数据
        """
        if not image_src:
            return ''

        if not variant_id:
            # 生成一个唯一临时id
            import uuid
            variant_id = str(uuid.uuid4())

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
                return ''

        # 2. 下载并处理新图片
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0',
                'Accept': 'image/webp,image/*,*/*;q=0.8'
            }

            with requests.get(image_src, stream=True) as r:
                r.raise_for_status()
                with open(temp_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)

            # 计算文件哈希用于验证
            # file_hash = hashlib.md5(response.content).hexdigest()
            # print(f"下载完成，文件哈希: {file_hash}")

            # 先保存到临时文件
            # with open(temp_path, 'wb') as f:
            #     f.write(response.content)

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

            _, _, tb = sys.exc_info()
            line_number = tb.tb_lineno
            # raise ValueError(f"图片处理失败line_number:{line_number}: {str(e)}")
            return ''
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

        return ''

    def _format_created_at(self, created_at):
        """格式化日期"""
        parsed_date = datetime.datetime.strptime(created_at, '%Y-%m-%dT%H:%M:%S.%fZ')
        formatted_date = parsed_date.strftime('%Y-%m-%d %H:%M:%S')
        return formatted_date

    def _create_order(self, data, customer_id, pricelist_id, currency_id):
        """创建订单"""
        try:
            order = data.get('order')

            formatted_date = self._format_created_at(order['created_at'])

            order_data = {
                'partner_id'    : int(customer_id),
                'origin'        : order['order_number'],
                'date_order'    : formatted_date,
                'state'         : 'sale',
                'create_date'   : formatted_date,
                'invoice_status': 'to invoice',
                'pricelist_id'  : pricelist_id,
                'currency_id'   : currency_id,
                'amount_total'  : float(order['grand_total']),
                'amount_tax'    : float(order['tax_amount']),
                'warehouse_id'  : self._get_warehouse_id(order),
                'name'          : order['name'],
                'website_id'    : self._get_website_id(order['website_name']),
            }
            new_order = request.env['sale.order'].sudo().create(order_data)
            # new_order.action_confirm()
        except Exception as e:
            _logger.error("Failed to _create_order: %s", str(e))
            raise ValueError("Failed to _create_order: %s", str(e))

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

        currency_str = order['currency']

        currency = request.env['res.currency'].sudo().search([('name', '=', order['currency'])], limit=1)
        if not currency:
            raise ValueError(f"找不到 currency = {currency_str} 的货币符号，请先创建")

        pricelist = request.env['product.pricelist'].sudo().search([
            ('currency_id', '=', currency.id)
        ], limit=1)
        if not pricelist:
            raise ValueError(f"找不到 currency = {currency_str} 的价格表，请先创建")


        if not currency:
            raise ValueError("Currency not found")

        return pricelist.id, currency.id

    def _get_state(self, data, country_id):
        """获取区域ID"""
        order = data.get('order')
        shipping_address = order.get('shipping_address')
        code = shipping_address.get('province')
        search_where = []
        if code:
            search_where.append(('code', '=', code))
        else:
            return False

        if country_id:
            search_where.append(('country_id', '=', country_id))

        state = request.env['res.country.state'].sudo().search(search_where, limit=1)
        if not state:
            state = request.env['res.country.state'].sudo().search([
                ('name', '=', shipping_address.get('state_name')),
                ('country_id', '=', country_id)
            ], limit=1)

        if not state:
            raise ValueError(f"State not found code={code} and country_id={country_id}")
        return state.id

    def _get_country(self, data):
        """获取国家ID"""
        order = data.get('order')
        country = request.env['res.country'].sudo().search([('code', '=', order['shipping_address']['country'])], limit=1)
        if not country:
            raise ValueError("Country not found")
        return country

    def _get_or_create_customer(self, data, state_id, country_id):
        """
        根据传入的数据创建或获取客户记录，支持多地址逻辑。
        :param data: dict，包含 'name', 'email' 等基本信息
        :param state_id: int，省份ID
        :param country_id: int，国家ID
        :return: res.partner 对象
        """

        order = data.get('order')
        customer = order.get('customer')
        customer_data = {
            'name'        : order['shipping_address']['first_name'] + ' ' + order['shipping_address']['last_name'],
            'email'       : customer['email'],
            'phone'       : order['shipping_address']['phone'],
            'street'      : order['shipping_address']['address1'],
            'city'        : order['shipping_address']['city'],
            'zip'         : order['shipping_address']['zip'],
            'country_code': order['shipping_address']['country'],

            'country_id'  : country_id,
            'website_id'  : config['usa_website_id'],
            'type'        : 'delivery',
        }

        if state_id:
            customer_data['state_id'] = state_id

        Partner = request.env['res.partner'].sudo()

        # 查找是否有同名同邮箱的主联系人
        existing_partner = Partner.search([
            ('email', '=', customer['email']),
            ('parent_id', '=', False)
        ], limit=1)

        # 如果不存在，创建主客户
        if not existing_partner:
            customer = Partner.create(customer_data)
            return customer

        # 检查是否已存在相同地区的记录（包括主记录或子地址）
        existing_same_area = Partner.search([
            ('parent_id', 'in', [existing_partner.id, False]),
            ('email', '=', customer['email']),
            ('state_id', '=', state_id),
            ('country_id', '=', country_id)
        ], limit=1)

        if existing_same_area:
            return existing_same_area

        # 创建新的子联系人（收货地址）
        customer_data.update({
            'parent_id': existing_partner.id,
        })
        new_address = Partner.create(customer_data)
        return new_address

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

    @http.route('/api/nexamerchant/sync_products', type='json', auth='public', methods=['POST'], csrf=False)
    def sync_products(self, **kwargs):
        data = request.httprequest.data
        if not data:
            return {
                'success': False,
                'message': 'No data provided',
                'status': 400
            }

        response = {
            'success': False,
            'message': '',
        }

        redis_host = config['redis_host']
        redis_port = config['redis_port']
        redis_db = config['redis_db']
        redis_password = config['redis_password']
        redis_obj = redis.Redis(host=redis_host, port=redis_port, db=redis_db, password=redis_password)
        redis_key = f'{config['odoo_product_id_hash_key']}:{config['app_env']}'

        try:
            product_info = json.loads(data)
            attributes = product_info.get('attributes', {})

            # 查找或创建spu
            default_code = product_info.get('default_code').lower()
            redis_field = f'{default_code}'
            product_template_id = redis_obj.hget(redis_key, redis_field)
            if not product_template_id:
                product_template = request.env['product.template'].sudo().search([
                    ('default_code', '=', default_code),
                ], limit=1)
                if not product_template:
                    product_template = request.env['product.template'].sudo().create({
                        'name': product_info.get('name', ''),
                        'description': product_info.get('description', ''),
                        'list_price': float(product_info.get('price', 0)),
                        'type': 'product',
                    })
                    product_template_id = product_template.id
                else:
                    product_template_id = product_template.id

                redis_obj.hset(redis_key, redis_field, int(product_template_id))
            else:
                product_template = request.env['product.template'].sudo().browse(int(product_template_id))

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
                        'default_code': product_info.get('product_sku')
                    })

            # 5. 更新变体信息
            update_vals = {
                'default_code': product_info.get('product_sku'),
            }
            if product_info.get('img'):
                image_base64 = self._get_product_img(variant.id, product_info.get('img'))
                if image_base64:
                    update_vals['image_1920'] = image_base64

            variant.sudo().write(update_vals)

            # 生成报关信息
            self._create_ext_product(variant.id, product_info)

            # 获取所有变体
            product_template = request.env['product.template'].sudo().browse(product_template_id)
            self._auto_fill_variant_default_codes(product_template)

            response['success'] = True

            return response

        except Exception as e:
            _, _, tb = sys.exc_info()
            line_number = tb.tb_lineno
            response['message'] = f"Failed to create product attributes---: { str(e)}. line_number: {line_number}"

        return response

    def _create_ext_product(self, variant_id, product):
        '''
        创建报关信息
        '''
        request.env['products_ext.products_ext'].sudo().search([
            ('product_id', '=', variant_id)
        ], limit=1) or request.env['products_ext.products_ext'].sudo().create({
            'product_id': variant_id,
            'product_url': product.get('product_url'),
            'declared_price': product.get('declared_price'),
            'declared_name_cn': product.get('declared_name_cn'),
            'declared_name_en': product.get('declared_name_en'),
        })

    @http.route('/api/nexamerchant/order/<int:order_id>', type='json', auth='public', methods=['PUT'], csrf=False)
    def update_order(self, order_id, **kwargs):
        # 处理更新订单的逻辑
        pass

    @http.route('/api/nexamerchant/order/<int:order_id>', type='http', auth='public', methods=['GET'], csrf=False)
    def get_order(self, order_id, **kwargs):
        print('hellow world')
        # 处理获取订单的逻辑
        pass