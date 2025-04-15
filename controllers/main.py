import json
from odoo import http
from odoo.http import request
from odoo.exceptions import UserError

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

    @http.route('/api/nexamerchant/order/<int:order_id>', type='json', auth='public', methods=['PUT'], csrf=False)
    def update_order(self, order_id, **kwargs):
        # 处理更新订单的逻辑
        pass

    @http.route('/api/nexamerchant/order/<int:order_id>', type='json', auth='public', methods=['GET'], csrf=False)
    def get_order(self, order_id):
        # 处理获取订单的逻辑
        pass

    @http.route('/api/nexamerchant/order/<int:order_id>', type='json', auth='public', methods=['DELETE'], csrf=False)
    def delete_order(self, order_id):
        # 处理删除订单的逻辑
        pass

    @http.route('/api/nexamerchant/product', type='json', auth='public', methods=['POST'])
    def create_product(self, **kwargs):
        # @link https://shopify.dev/docs/api/admin-rest/2025-01/resources/product
        try:
            data = json.loads(request.httprequest.data)
            

            # Basic validation
            if not data or not data.get('product_id') or not data.get('title'):
                return {'success': False, 'message': 'Missing product_id or title in request'}

            # Call the model method to handle product creation/update logic
            product_api_logic = request.env['product.api.logic']
            product = product_api_logic.create_or_update_product(data)

            return {'success': True, 'message': f'Product created/updated successfully. Product ID: {product.id}'}

        except UserError as e:  # Catch UserError from the model
            return {'success': False, 'message': str(e)}
        except Exception as e:
            return {'success': False, 'message': f'An unexpected error occurred: {str(e)}'}

        pass