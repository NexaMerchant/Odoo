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

    @http.route('/api/nexamerchant/product', type='json', auth='public', methods=['POST'], csrf=False)
    def create_product(self, **kwargs):
        # 处理创建产品的逻辑
        # @link https://shopify.dev/docs/api/admin-rest/2025-01/resources/product

        # Get all the product data from the request


        # Create the product in the database
        # Return the product data in the response

        try:

          request_data = json.loads(request.httprequest.data)

          sku = request_data.get('sku')

          # base use sku to search the odoo product
          # if not exist create product
          # if exist update product

          product = request.env['product.product'].search([('default_code', '=', sku)])

          if not product:
              product = request.env['product.product'].create({'default_code': sku})

              # add variant to product
              # add price to product
              # add name to product
              # add description to product
              # add image to product
   
          else:




          return {"sku": sku}

        except Exception as e:
            return {'error': str(e)}
        pass