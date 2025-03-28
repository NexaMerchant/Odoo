import json
from odoo import http
from odoo.http import request
from odoo.exceptions import UserError

class ProductController(http.Controller):

    @http.route('/api/nexamerchant/product', type='json', auth='public', methods=['POST'], csrf=False, cors='*')
    def create_product(self, **kwargs):
        api_key = kwargs.get('api_key')
        # post data to create product like shopify admin api create product
        # https://shopify.dev/docs/api/admin-rest/2025-01/resources/product#create-2025-01
        # Get all the product data from the request
        # Create the product in the database
        # Return the product data in the response
        try:
            request_data = json.loads(request.httprequest.data)

            product = request_data.get('product')

            # create product in odoo

            return {'product': product}
        except Exception as e:
            return {'error': str(e)}

        return {'product': request_data}

        pass

    @http.route('/api/nexamerchant/product/<int:product_id>', type='json', auth='public', methods=['PUT'], csrf=False)
    def update_product(self, product_id, **kwargs):
        # 处理更新产品的逻辑
        pass

    @http.route('/api/nexamerchant/product/<int:product_id>', type='json', auth='public', methods=['GET'], csrf=False)
    def get_product(self, product_id, **kwargs):
        # 处理获取产品的逻辑
        pass