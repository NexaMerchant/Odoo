import json
from odoo import http
from odoo.http import request

class OrderController(http.Controller):
    _name = 'nexamerchant.order'
    _description = 'Order Management'

    @http.route('/api/nexamerchant/order', type='json', auth='public', methods=['POST'], csrf=False, cors='*')
    def create_order(self, **kwargs):
        api_key = kwargs.get('api_key')
        # post data to create order like shopify admin api create order
        # https://shopify.dev/docs/api/admin-rest/2025-01/resources/order#create-2025-01
        # Get all the order data from the request
        # Create the order in the database
        # Return the order data in the response
        try:
            request_data = json.loads(request.httprequest.data)

            order = request_data.get('order')

            order_lines = order.get('order_lines')

            # create product in odoo

            # create order in odoo

            # create order line in odoo

            # create customer in odoo

            # create shipping address in odoo

            # create billing address in odoo

            # create payment in odoo



            return {'order': order}
        except Exception as e:
            return {'error': str(e)}




        return {'order': request_data}




        pass

    @http.route('/api/order/<int:order_id>', type='json', auth='public', methods=['PUT'], csrf=False)
    def update_order(self, order_id, **kwargs):
        # 处理更新订单的逻辑
        pass

    @http.route('/api/order/<int:order_id>', type='json', auth='public', methods=['GET'], csrf=False)
    def get_order(self, order_id):
        # 处理获取订单的逻辑
        pass