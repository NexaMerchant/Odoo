import json
from odoo import http, fields
from odoo.http import request, Response
from odoo.exceptions import UserError, AccessError,AccessDenied
import werkzeug
import logging
from dotenv import load_dotenv
import os

_logger = logging.getLogger(__name__)

load_dotenv()

class OrderController(http.Controller):
    _name = 'nexamerchant.order'
    _description = 'Order Management'

    @http.route('/api/nexamerchant/order', type='json', auth='public', methods=['POST'], csrf=True, cors='*')
    def create_order(self, **kwargs):
        """
        创建订单接口
        返回格式: {
            'success': bool,
            'message': str,
            'order_code': str,
            'order_id': int
        }
        """
        response = {
            'success': False,
            'message': '',
            'order_code': '',
            'order_id': 0
        }

        # return response

        try:
            # 获取请求数据
            data = request.httprequest.data
            if not data:
                return Response(
                    json.dumps({'success': False, 'message': 'No data provided'}),
                    content_type='application/json',
                    status=400
                )

            data = json.loads(data)
            order = data.get('order')

            # 获取国家id
            country_id = self._get_country_id(data)

            # 获取区域id
            state_id = self._get_state_id(data, country_id)

            # 获取客户id
            customer_id = self._get_customer_id(data, state_id, country_id)

            # 获取货币id
            currency_id = self._get_currency_id(data)

            order_info = request.env['sale.order'].search('sale.order', [
                ['origin', '=', order['id']],
            ])

            if order_info:
                # 更新
                order.write({
                    'currency_id': currency_id.id,
                    'name': os.getenv('USA_ORDER_PREFIX') + str(order['id']),
                })
                order_id = order_info[0].id
            else:
                # 创建order
                # create a new order
                order_id = self._create_order(data, customer_id, currency_id)

            for item in order['lines']:
                # 获取产品id
                product_info = request.env['product.template'].search([
                    ['default_code', '=', item['product_code']],
                ])

            # return data

            # 1. 数据验证
            # self._validate_order_data(data)

            # 2. 准备订单数据
            order_vals = self._prepare_order_vals(data)
            # return order_vals

            # 3. 创建订单
            order = self._create_order_record(order_vals)

            # 4. 处理订单行项目
            self._process_order_lines(data.get('lines', []), order)

            # 5. 其他后处理（如库存、支付等）
            self._post_process_order(order)

            # 构建成功响应
            response.update({
                'success': True,
                'message': '订单创建成功',
                'order_code': order.name,
                'order_id': order.id
            })

        except ValueError as ve:
            response['message'] = f"数据验证错误: {str(ve)}"
            _logger.error(f"订单创建失败 - 验证错误: {str(ve)}")

        except Exception as e:
            response['message'] = f"订单创建失败 - 系统错误: {str(e)}"
            _logger.exception(f"订单创建失败 - 系统错误: {str(e)}")

        return response

    def _create_product_record(self, item):
        """
        1.商品属性: product.attribute
        2.属性值: product.attribute.value
        3.商品模板(spu): product.template
        4.商品模板允许的属性: product.template.attribute.line
        5.商品模板允许的属性的值: product.template.attribute.value
        6.商品变体(sku): product.product(根据笛卡尔积自动生成记录)
        """

        self._create_product_attributes(item)

        """update_product_variants ToDo"""



    def _create_product_attributes(self, item):
        """
        product.attribute
        product.attribute.value
        """
        sku = item.get('sku')
        attributes = sku.get('attributes')
        for key, attribute in attributes.items():
            # 1. 查找或创建属性
            product_attribute = request.env['product.attribute'].search([
                ('name', '=', attribute.get('attribute_name')),
                ('create_variant', '=', 'always')
            ], limit=1)

            if not product_attribute:
                product_attribute = request.env['product.attribute'].sudo().create({
                    'name': attribute.get('attribute_name'),
                    'create_variant': 'always',
                })

            # 2. 查找或创建属性值
            attribute_value = request.env['product.attribute.value'].search([
                ('name', '=', attribute.get('option_label')),
                ('attribute_id', '=', product_attribute.id)
            ], limit=1)

            if not attribute_value:
                request.env['product.attribute.value'].sudo().create({
                    'name': attribute.get('option_label'),
                    'attribute_id': product_attribute.id
                })

            # 3. 查找或创建商品模板
            product_template = request.env['product.template'].search([
                ('default_code', '=', attribute.get('product_id')),
            ], limit=1)
            if not product_template:
                product_template = request.env['product.template'].sudo().create({
                    'name': item['title'],
                    'description': item['name'],
                    'list_price': sku['price'],
                    'compare_list_price': item['price'],
                    'type': 'consu',
                    'default_code': int(attribute.get('product_id')),
                    'barcode': str(attribute.get('product_id')),
                    'website_id': int(os.getenv('USA_WEBSITE_ID')),
                    "responsible_id": 17,
                    "is_storable": True,
                })

            # 4. 查找或创建商品模板允许的属性
            product_attribute_line = request.env['product.template.attribute.line'].search([
                ('product_tmpl_id', '=', product_template.id),
                ('attribute_id', '=', product_attribute.id)
            ], limit=1)
            if not product_attribute_line:
                request.env['product.template.attribute.line'].sudo().create({
                    'attribute_id': product_attribute.id,
                    'value_ids': [(6, 0, [attribute_value.id])],
                })


    def _create_order(self, data, customer_id, currency_id):
        order = data.get('order')
        order_data = {
            'partner_id'    : int(customer_id),
            'origin'        : order['id'],
            'date_order'    : order['created_at'],
            'website_id'    : int(os.getenv('USA_WEBSITE_ID')),
            'state'         : 'sale',
            'create_date'   : fields.Datetime.now(),
            'invoice_status': 'to invoice',
            "currency_id"   : currency_id,
            'amount_total'  : order['grand_total'],
            'amount_tax'    : order['tax_amount'],
            'name'          : os.getenv('USA_ORDER_PREFIX') + str(order['id']),
            'warehouse_id'  : 4,
            'company_id'    : 5,
        }

        print(order_data)

        order = request.env['sale.order'].sudo().create(order_data)

        return order.id

    def _get_currency_id(self, data):
        order = data.get('order')
        currency = request.env['res.currency'].search([('name', '=', order['order_currency_code'])])
        if not currency:
            raise ValueError("Currency not found")
        return currency[0].id

    def _get_state_id(self, data, country_id):
        """获取区域ID"""
        order = data.get('order')
        shipping_address = order.get('shipping_address')
        code = shipping_address.get('state')
        if not code:
            code = shipping_address.get('country')

        state = request.env['res.country.state'].search([
            [
                ('code', '=', code),
                ('country_id', '=', country_id)
            ],
        ])
        if not state:
            raise ValueError("State not found")
        return state[0].id

    def _get_country_id(self, data):
        """获取国家ID"""
        order = data.get('order')
        country = request.env['res.country'].search([('code', '=', order['shipping_address']['country'])])
        if not country:
            raise ValueError("Country not found")
        return country[0].id

    def _get_customer_id(self, data, state_id, country_id):
        """获取客户ID"""
        order = data.get('order')
        customer = order.get('customer')
        customer_info = request.env['res.partner'].search([('email', '=', customer.get('email'))])
        if customer_info:
            customer_id = customer_info[0].id
        else:
            print("Customer not found.")
            # create a new customer
            customer_data = {
                'name'        : order['shipping_address']['first_name'] + ' ' + order['shipping_address']['last_name'],
                'email'       : order['customer_email'],
                'phone'       : order['shipping_address']['phone'],
                'street'      : order['shipping_address']['address1'],
                'city'        : order['shipping_address']['city'],
                'zip'         : order['shipping_address']['postcode'],
                'country_code': order['shipping_address']['country'],
                'state_id'    : state_id,
                'country_id'  : country_id,
                'website_id'  : os.getenv('USA_WEBSITE_ID'),
                'lang'        : os.getenv('USA_LANG'),
                'category_id' : [8],
                'type'        : 'delivery',
            }

            print(customer_data)

            customer_id = request.env['res.partner'].sudo().create(customer_data)

        return customer_id

    def _validate_order_data(self, data):
        """验证订单数据"""
        required_fields = ['lines']
        for field in required_fields:
            if field not in data:
                raise ValueError(f"缺少必填字段: {field}")

        if not isinstance(data.get('lines'), list) or len(data['lines']) == 0:
            raise ValueError("订单必须包含至少一个商品")

    def _prepare_order_vals(self, data):
        """准备订单创建字典"""
        partner = request.env['res.partner'].browse(data['customer_id'])
        if not partner.exists():
            raise ValueError("客户不存在")

        return {
            'partner_id': data['customer_id'],
            'date_order': fields.Datetime.now(),
            'note': data.get('note', ''),
            'user_id': request.env.user.id,
            'team_id': self._get_sales_team(data),
            # 其他必要字段...
        }



    @http.route('/api/nexamerchant/order_bak', type='json', auth='public', methods=['POST'], csrf=True, cors='*')
    def create_order_bak(self, **kwargs):
        api_key = kwargs.get('api_key')

        api_key = request.httprequest.headers.get('X-API-Key')
        if not api_key:
            raise AccessDenied("API key required")

        # Use request.update_env to set the user
        request.update_env(user=2)

        # post data to create order like shopify admin api create order
        # https://shopify.dev/docs/api/admin-rest/2025-01/resources/order#create-2025-01
        # Get all the order data from the request
        # Create the order in the database
        # Return the order data in the response
        try:
            request_data = json.loads(request.httprequest.data)

            order = request_data.get('order')

            order_lines = order.get('order_lines')

            # create customer in odoo
            customer = order.get('customer')
            # search customer by email
            customer_id = request.env['res.partner'].search([('email', '=', customer.get('email'))])
            if not customer_id:
                try:
                    # Create new customer if not found
                    customerdata = {
                        'name': customer.get('first_name') + ' ' + customer.get('last_name'),
                        'email': customer.get('email')
                    }
                    customer_id = request.env['res.partner'].sudo().create(customerdata)
                except AccessError:
                    raise UserError('You do not have the necessary permissions to create a customer.')
            else:
                customer_id = customer_id[0]
            print(customer_id)

            print(request.env.user)




            return {'order': order}
        except UserError as e:
            return {'error': str(e)}
        except Exception as e:
            return {'error': f'An unexpected error occurred: {str(e)}'}

        return {'order': request_data}

        pass

    @http.route('/api/nexamerchant/order/<int:order_id>', type='json', auth='public', methods=['PUT'], csrf=False)
    def update_order(self, order_id, **kwargs):
        # 处理更新订单的逻辑
        pass

    @http.route('/api/nexamerchant/order/<int:order_id>', type='http', auth='public', methods=['GET'], csrf=False)
    def get_order(self, order_id, **kwargs):
        print('hellow world')
        # 处理获取订单的逻辑
        pass