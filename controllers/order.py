import json
from odoo import http
from odoo.http import request
from odoo.exceptions import UserError, AccessError,AccessDenied
import werkzeug

class OrderController(http.Controller):
    _name = 'nexamerchant.order'
    _description = 'Order Management'

    @http.route('/api/nexamerchant/order', type='json', auth='public', methods=['POST'], csrf=True, cors='*')
    def create_order(self, **kwargs):
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

    @http.route('/api/nexamerchant/order/<int:order_id>', type='json', auth='public', methods=['GET'], csrf=False)
    def get_order(self, order_id, **kwargs):
        # 处理获取订单的逻辑
        pass